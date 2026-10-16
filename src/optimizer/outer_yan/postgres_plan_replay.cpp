#include "duckdb/optimizer/outer_yan/postgres_plan_replay.hpp"

#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/catalog/catalog_entry/schema_catalog_entry.hpp"
#include "duckdb/common/enum_util.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/file_system.hpp"
#include "duckdb/common/printer.hpp"
#include "duckdb/common/string_util.hpp"
#include "duckdb/main/client_config.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/optimizer/outer_yan/pipeline/simplification.hpp"
#include "duckdb/parser/constraints/unique_constraint.hpp"
#include "duckdb/planner/column_binding_map.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/logical_operator_visitor.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_explain.hpp"
#include "duckdb/planner/operator/logical_filter.hpp"
#include "duckdb/planner/operator/logical_get.hpp"
#include "duckdb/planner/operator/logical_projection.hpp"
#include "mbedtls_wrapper.hpp"
#include "yyjson.hpp"

#include <algorithm>
#include <functional>
#include <sstream>

namespace duckdb {
namespace {

using namespace duckdb_yyjson; // NOLINT

static constexpr const char *REPLAY_FORMAT = "duckyan.pg_join_tree.v1";
static constexpr const char *QUERY_CANONICALIZATION = "duckyan.sql_text.v1";
static constexpr int64_t REQUIRED_POSTGRES_VERSION = 160002;
static constexpr idx_t MAX_ARTIFACT_BYTES = 16ULL * 1024ULL * 1024ULL;
static constexpr idx_t MAX_ARTIFACT_NODES = 4096;

struct ReplayNode {
	enum class Type : uint8_t { SCAN, JOIN };

	Type type;
	string schema;
	string relation;
	string alias;
	idx_t occurrence = 0;
	bool has_occurrence = false;
	JoinType join_type = JoinType::INVALID;
	unique_ptr<ReplayNode> left;
	unique_ptr<ReplayNode> right;
};

struct ReplayArtifact {
	string path;
	string query_sha256;
	string plan_data;
	string plan_schema;
	unique_ptr<ReplayNode> tree;
	vector<ReplayNode *> scans;
	idx_t scan_count = 0;
	idx_t join_count = 0;
};

struct TreeSignatures {
	string raw;
	string semantic;
};

struct SourceJoin {
	unique_ptr<OTJoin> info;
};

struct BuiltSubtree {
	unique_ptr<OTNode> node;
	unordered_set<idx_t> relations;
};

struct DuckScanInventory {
	unordered_map<idx_t, idx_t> occurrence_by_table_index;
	unordered_map<string, idx_t> table_index_by_identity;
	unordered_map<string, idx_t> count_by_base;
	unordered_map<idx_t, const LogicalGet *> get_by_table_index;
};

[[noreturn]] static void ReplayError(const string &path, const string &message) {
	throw InvalidInputException("[PGPLAN] artifact \"%s\": %s", path.c_str(), message.c_str());
}

static bool IsASCIIWhitespace(char c) {
	switch (c) {
	case ' ':
	case '\t':
	case '\n':
	case '\r':
	case '\f':
	case '\v':
		return true;
	default:
		return false;
	}
}

static bool IsASCIIIdentifierStart(char c) {
	return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_';
}

static bool IsASCIIIdentifierContinuation(char c) {
	return IsASCIIIdentifierStart(c) || (c >= '0' && c <= '9');
}

static idx_t DollarDelimiterLength(const string &text, idx_t index, idx_t end) {
	if (text[index] != '$' || index + 1 >= end) {
		return 0;
	}
	if (text[index + 1] == '$') {
		return 2;
	}
	if (!IsASCIIIdentifierStart(text[index + 1])) {
		return 0;
	}
	idx_t cursor = index + 2;
	while (cursor < end && IsASCIIIdentifierContinuation(text[cursor])) {
		cursor++;
	}
	return cursor < end && text[cursor] == '$' ? cursor - index + 1 : 0;
}

static idx_t FirstSQLTokenOffset(const string &text, idx_t begin, idx_t end) {
	auto index = begin;
	while (index < end) {
		while (index < end && IsASCIIWhitespace(text[index])) {
			index++;
		}
		if (index + 1 >= end) {
			return index;
		}
		if (text[index] == '-' && text[index + 1] == '-') {
			index += 2;
			while (index < end && text[index] != '\n' && text[index] != '\r') {
				index++;
			}
			continue;
		}
		if (text[index] != '/' || text[index + 1] != '*') {
			return index;
		}
		const auto comment_begin = index;
		idx_t depth = 1;
		index += 2;
		while (index < end && depth > 0) {
			if (index + 1 < end && text[index] == '/' && text[index + 1] == '*') {
				depth++;
				index += 2;
			} else if (index + 1 < end && text[index] == '*' && text[index + 1] == '/') {
				depth--;
				index += 2;
			} else {
				index++;
			}
		}
		if (depth != 0) {
			// DuckDB rejects an unterminated comment before optimization. Returning
			// its start is nevertheless fail-closed if a malformed string reaches
			// this helper through a future call path: it cannot match capture.
			return comment_begin;
		}
	}
	return index;
}

static optional_idx TerminalTopLevelSemicolon(const string &text, idx_t begin, idx_t end) {
	enum class LexState : uint8_t { NORMAL, SINGLE_QUOTE, DOUBLE_QUOTE, LINE_COMMENT, BLOCK_COMMENT, DOLLAR };
	LexState state = LexState::NORMAL;
	idx_t block_depth = 0;
	idx_t semicolon_count = 0;
	idx_t semicolon_position = 0;
	string dollar_delimiter;

	for (idx_t index = begin; index < end; index++) {
		const auto current = text[index];
		const auto next = index + 1 < end ? text[index + 1] : '\0';
		switch (state) {
		case LexState::NORMAL:
			if (current == '\'') {
				state = LexState::SINGLE_QUOTE;
			} else if (current == '"') {
				state = LexState::DOUBLE_QUOTE;
			} else if (current == '-' && next == '-') {
				state = LexState::LINE_COMMENT;
				index++;
			} else if (current == '/' && next == '*') {
				state = LexState::BLOCK_COMMENT;
				block_depth = 1;
				index++;
			} else if (current == '$') {
				auto delimiter_length = DollarDelimiterLength(text, index, end);
				if (delimiter_length > 0) {
					dollar_delimiter = text.substr(index, delimiter_length);
					state = LexState::DOLLAR;
					index += delimiter_length - 1;
				}
			} else if (current == ';') {
				semicolon_count++;
				semicolon_position = index;
			}
			break;
		case LexState::SINGLE_QUOTE:
			if (current == '\'' && next == '\'') {
				index++;
			} else if (current == '\'') {
				state = LexState::NORMAL;
			}
			break;
		case LexState::DOUBLE_QUOTE:
			if (current == '"' && next == '"') {
				index++;
			} else if (current == '"') {
				state = LexState::NORMAL;
			}
			break;
		case LexState::LINE_COMMENT:
			if (current == '\r' || current == '\n') {
				state = LexState::NORMAL;
			}
			break;
		case LexState::BLOCK_COMMENT:
			if (current == '/' && next == '*') {
				block_depth++;
				index++;
			} else if (current == '*' && next == '/') {
				block_depth--;
				index++;
				if (block_depth == 0) {
					state = LexState::NORMAL;
				}
			}
			break;
		case LexState::DOLLAR:
			if (text.compare(index, dollar_delimiter.size(), dollar_delimiter) == 0) {
				index += dollar_delimiter.size() - 1;
				dollar_delimiter.clear();
				state = LexState::NORMAL;
			}
			break;
		}
	}
	if (semicolon_count == 1 && semicolon_position + 1 == end) {
		return optional_idx(semicolon_position);
	}
	return optional_idx();
}

static string CanonicalizeQuery(const string &query) {
	// The capture tool applies the same byte-level rule before SHA-256. DuckDB
	// exposes an active statement beginning at its first SQL token, so leading
	// whitespace/comments are deliberately outside the hashed representation.
	string normalized;
	normalized.reserve(query.size());
	for (idx_t i = 0; i < query.size(); i++) {
		if (query[i] == '\r') {
			normalized.push_back('\n');
			if (i + 1 < query.size() && query[i + 1] == '\n') {
				i++;
			}
		} else {
			normalized.push_back(query[i]);
		}
	}

	idx_t end = normalized.size();
	while (end > 0 && IsASCIIWhitespace(normalized[end - 1])) {
		end--;
	}
	idx_t begin = FirstSQLTokenOffset(normalized, 0, end);
	auto terminal_semicolon = TerminalTopLevelSemicolon(normalized, begin, end);
	if (terminal_semicolon.IsValid()) {
		end = terminal_semicolon.GetIndex();
		while (end > begin && IsASCIIWhitespace(normalized[end - 1])) {
			end--;
		}
	}
	return normalized.substr(begin, end - begin);
}

static string QuerySHA256(const string &query) {
	auto hash = duckdb_mbedtls::MbedTlsWrapper::ComputeSha256Hash(CanonicalizeQuery(query));
	string hex(duckdb_mbedtls::MbedTlsWrapper::SHA256_HASH_LENGTH_TEXT, '\0');
	duckdb_mbedtls::MbedTlsWrapper::ToBase16(&hash[0], &hex[0], hash.size());
	return hex;
}

static bool ASCIIEqualNoCase(const string &text, idx_t offset, const char *expected) {
	for (idx_t index = 0; expected[index] != '\0'; index++) {
		if (offset + index >= text.size()) {
			return false;
		}
		auto actual = text[offset + index];
		if (actual >= 'A' && actual <= 'Z') {
			actual = static_cast<char>(actual - 'A' + 'a');
		}
		if (actual != expected[index]) {
			return false;
		}
	}
	return true;
}

static string ExtractPlainExplainInnerQuery(const string &query, const string &artifact_path) {
	idx_t offset = 0;
	while (offset < query.size() && IsASCIIWhitespace(query[offset])) {
		offset++;
	}
	static constexpr idx_t EXPLAIN_LENGTH = 7;
	if (!ASCIIEqualNoCase(query, offset, "explain") || offset + EXPLAIN_LENGTH >= query.size() ||
	    !IsASCIIWhitespace(query[offset + EXPLAIN_LENGTH])) {
		ReplayError(artifact_path,
		            "hash verification supports only a plain EXPLAIN followed by the captured query");
	}
	offset += EXPLAIN_LENGTH;
	while (offset < query.size() && IsASCIIWhitespace(query[offset])) {
		offset++;
	}
	if (offset >= query.size() || query[offset] == '(') {
		ReplayError(artifact_path,
		            "hash verification supports only plain EXPLAIN; EXPLAIN options are unsupported");
	}
	return query.substr(offset);
}

static bool IsLowerHexSHA256(const string &value) {
	if (value.size() != 64) {
		return false;
	}
	for (auto c : value) {
		if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
			return false;
		}
	}
	return true;
}

static string JSONQuote(const string &input) {
	std::ostringstream result;
	result << '"';
	for (const auto c : input) {
		switch (c) {
		case '"':
			result << "\\\"";
			break;
		case '\\':
			result << "\\\\";
			break;
		case '\b':
			result << "\\b";
			break;
		case '\f':
			result << "\\f";
			break;
		case '\n':
			result << "\\n";
			break;
		case '\r':
			result << "\\r";
			break;
		case '\t':
			result << "\\t";
			break;
		default:
			if (static_cast<uint8_t>(c) < 0x20) {
				result << StringUtil::Format("\\u%04x", static_cast<uint8_t>(c));
			} else {
				result << c;
			}
			break;
		}
	}
	result << '"';
	return result.str();
}

static yyjson_val *RequireObjectField(yyjson_val *object, const char *key, const string &path) {
	auto value = yyjson_obj_get(object, key);
	if (!value || !yyjson_is_obj(value)) {
		ReplayError(path, StringUtil::Format("field \"%s\" must be an object", key));
	}
	return value;
}

static string RequireStringField(yyjson_val *object, const char *key, const string &path) {
	auto value = yyjson_obj_get(object, key);
	if (!value || !yyjson_is_str(value)) {
		ReplayError(path, StringUtil::Format("field \"%s\" must be a string", key));
	}
	const auto text = yyjson_get_str(value);
	if (!text) {
		ReplayError(path, StringUtil::Format("field \"%s\" has no string value", key));
	}
	return string(text, yyjson_get_len(value));
}

static JoinType ParseJoinType(const string &value, const string &path) {
	if (value == "inner") {
		return JoinType::INNER;
	}
	if (value == "left") {
		return JoinType::LEFT;
	}
	if (value == "right") {
		return JoinType::RIGHT;
	}
	if (value == "full") {
		return JoinType::OUTER;
	}
	ReplayError(path, "join_type must be one of inner, left, right, or full");
}

static string JoinToken(JoinType type) {
	switch (type) {
	case JoinType::INNER:
		return "inner";
	case JoinType::LEFT:
		return "left";
	case JoinType::RIGHT:
		return "right";
	case JoinType::OUTER:
		return "full";
	default:
		throw InvalidInputException("[PGPLAN] unsupported join kind %s", EnumUtil::ToString(type));
	}
}

static string NormalizedScanSignature(string normalized_schema, const string &relation) {
	auto normalized_relation = StringUtil::Lower(relation);
	return StringUtil::Format("S%llu:%s/%llu:%s", normalized_schema.size(), normalized_schema,
	                          normalized_relation.size(), normalized_relation);
}

static string ScanOccurrenceSignature(const string &base_signature, idx_t occurrence) {
	return StringUtil::Format("%s#%llu", base_signature, occurrence);
}

static string ArtifactScanSignature(const string &schema, const string &relation) {
	auto normalized_schema = StringUtil::Lower(schema);
	// PostgreSQL's ordinary default namespace maps to DuckDB's default
	// namespace. A PostgreSQL schema literally named "main" is not default.
	if (normalized_schema == "public") {
		normalized_schema = "$default";
	}
	return NormalizedScanSignature(std::move(normalized_schema), relation);
}

static string DuckScanSignature(const string &schema, const string &relation) {
	auto normalized_schema = StringUtil::Lower(schema);
	// Conversely, only DuckDB's own default schema is canonicalized. A DuckDB
	// schema literally named "public" remains a distinct, non-default schema.
	if (normalized_schema == "main") {
		normalized_schema = "$default";
	}
	return NormalizedScanSignature(std::move(normalized_schema), relation);
}

static string ArtifactScanIdentity(const ReplayNode &node) {
	return ScanOccurrenceSignature(ArtifactScanSignature(node.schema, node.relation), node.occurrence);
}

static TreeSignatures JoinSignatures(JoinType type, TreeSignatures left, TreeSignatures right) {
	TreeSignatures result;
	result.raw = "J[" + JoinToken(type) + "](" + left.raw + "," + right.raw + ")";
	switch (type) {
	case JoinType::INNER:
	case JoinType::OUTER: {
		if (right.semantic < left.semantic) {
			std::swap(left.semantic, right.semantic);
		}
		result.semantic = (type == JoinType::INNER ? "I(" : "F(") + left.semantic + "," + right.semantic + ")";
		break;
	}
	case JoinType::LEFT:
		result.semantic = "O(" + left.semantic + "," + right.semantic + ")";
		break;
	case JoinType::RIGHT:
		result.semantic = "O(" + right.semantic + "," + left.semantic + ")";
		break;
	default:
		throw InvalidInputException("[PGPLAN] unsupported join kind %s", EnumUtil::ToString(type));
	}
	return result;
}

static TreeSignatures ArtifactSignatures(const ReplayNode &node) {
	if (node.type == ReplayNode::Type::SCAN) {
		auto signature = ArtifactScanIdentity(node);
		return {signature, signature};
	}
	return JoinSignatures(node.join_type, ArtifactSignatures(*node.left), ArtifactSignatures(*node.right));
}

static unique_ptr<ReplayNode> ParseReplayNode(yyjson_val *value, ReplayArtifact &artifact,
	                                          unordered_set<string> &aliases,
	                                          idx_t depth) {
	if (!value || !yyjson_is_obj(value)) {
		ReplayError(artifact.path, "every tree node must be an object");
	}
	if (artifact.scan_count + artifact.join_count >= MAX_ARTIFACT_NODES || depth >= MAX_ARTIFACT_NODES) {
		ReplayError(artifact.path, "tree exceeds the v1 node limit");
	}
	auto op = RequireStringField(value, "op", artifact.path);
	if (op == "scan") {
		auto node = make_uniq<ReplayNode>();
		node->type = ReplayNode::Type::SCAN;
		node->schema = RequireStringField(value, "schema", artifact.path);
		node->relation = RequireStringField(value, "relation", artifact.path);
		node->alias = RequireStringField(value, "alias", artifact.path);
		if (node->schema.empty() || node->relation.empty() || node->alias.empty()) {
			ReplayError(artifact.path, "scan schema, relation, and alias must be non-empty");
		}
		if (node->schema != "public") {
			ReplayError(artifact.path, "tree scan schema must be the normalized DuckDB schema public");
		}
		auto occurrence = yyjson_obj_get(value, "occurrence");
		if (occurrence) {
			if (!yyjson_is_int(occurrence) || yyjson_get_sint(occurrence) < 0) {
				ReplayError(artifact.path, "scan occurrence must be a nonnegative integer");
			}
			node->occurrence = static_cast<idx_t>(yyjson_get_sint(occurrence));
			node->has_occurrence = true;
		}
		auto alias_key = StringUtil::Lower(node->alias);
		if (!aliases.insert(alias_key).second) {
			ReplayError(artifact.path, "scan alias is not unique: " + node->alias);
		}
		artifact.scan_count++;
		artifact.scans.push_back(node.get());
		return node;
	}
	if (op == "join") {
		auto node = make_uniq<ReplayNode>();
		node->type = ReplayNode::Type::JOIN;
		node->join_type = ParseJoinType(RequireStringField(value, "join_type", artifact.path), artifact.path);
		auto left = yyjson_obj_get(value, "left");
		auto right = yyjson_obj_get(value, "right");
		if (!left || !right) {
			ReplayError(artifact.path, "join node requires left and right children");
		}
		artifact.join_count++;
		node->left = ParseReplayNode(left, artifact, aliases, depth + 1);
		node->right = ParseReplayNode(right, artifact, aliases, depth + 1);
		return node;
	}
	ReplayError(artifact.path, "tree op must be \"scan\" or \"join\"");
}

static string ReadArtifactFile(ClientContext &context, const string &path) {
	auto &fs = FileSystem::GetFileSystem(context);
	auto handle = fs.OpenFile(path, FileFlags::FILE_FLAGS_READ);
	auto file_size = handle->GetFileSize();
	if (file_size == 0) {
		ReplayError(path, "file is empty");
	}
	if (file_size > MAX_ARTIFACT_BYTES) {
		ReplayError(path, "file exceeds the 16 MiB v1 limit");
	}
	string content(file_size, '\0');
	// The positional overload guarantees an exact read and throws if the file
	// is truncated or otherwise short after GetFileSize.
	fs.Read(*handle, &content[0], file_size, 0);
	return content;
}

static string SamplePlanFamily(const string &plan_data) {
	for (const auto &family : {"graph", "tpcds", "job"}) {
		const string prefix = string(family) + "-duckdb-sample-";
		if (plan_data.size() <= prefix.size() || plan_data.compare(0, prefix.size(), prefix) != 0) {
			continue;
		}
		const auto scale = plan_data.substr(prefix.size());
		if (scale.empty() || scale[0] < '1' || scale[0] > '9') {
			return string();
		}
		for (auto character : scale) {
			if (character < '0' || character > '9') {
				return string();
			}
		}
		return family;
	}
	return string();
}

static string FullPlanFamily(const string &plan_data) {
	for (const auto &family : {"tpch", "tpcds", "job"}) {
		if (plan_data == string(family) + "-duckdb-full") {
			return family;
		}
	}
	return string();
}

static void ValidateArtifactOccurrences(ReplayArtifact &artifact) {
	unordered_map<string, idx_t> counts;
	for (const auto scan : artifact.scans) {
		counts[ArtifactScanSignature(scan->schema, scan->relation)]++;
	}
	unordered_set<string> identities;
	for (auto scan : artifact.scans) {
		auto base = ArtifactScanSignature(scan->schema, scan->relation);
		if (!scan->has_occurrence && counts[base] != 1) {
			ReplayError(artifact.path,
			            "scan occurrence is required when a base relation appears more than once: " + scan->schema +
			                "." + scan->relation);
		}
		if (!identities.insert(ArtifactScanIdentity(*scan)).second) {
			ReplayError(artifact.path, "duplicate scan relation/occurrence identity: " + scan->schema + "." +
			                               scan->relation + "#" + to_string(scan->occurrence));
		}
	}
}

static ReplayArtifact ReadArtifact(ClientContext &context, const string &path) {
	ReplayArtifact artifact;
	artifact.path = path;
	auto content = ReadArtifactFile(context, path);
	unique_ptr<yyjson_doc, void (*)(yyjson_doc *)> document(
	    yyjson_read(content.c_str(), content.size(), YYJSON_READ_NOFLAG), yyjson_doc_free);
	if (!document) {
		ReplayError(path, "invalid JSON");
	}
	auto root = yyjson_doc_get_root(document.get());
	if (!root || !yyjson_is_obj(root)) {
		ReplayError(path, "JSON root must be an object");
	}
	if (RequireStringField(root, "format", path) != REPLAY_FORMAT) {
		ReplayError(path, StringUtil::Format("format must be %s", REPLAY_FORMAT));
	}
	artifact.query_sha256 = RequireStringField(root, "query_sha256", path);
	if (!IsLowerHexSHA256(artifact.query_sha256)) {
		ReplayError(path, "query_sha256 must be exactly 64 lowercase hexadecimal characters");
	}
	if (RequireStringField(root, "query_sha256_canonicalization", path) != QUERY_CANONICALIZATION) {
		ReplayError(path, StringUtil::Format("query_sha256_canonicalization must be %s",
		                                     QUERY_CANONICALIZATION));
	}
	auto postgres = RequireObjectField(root, "postgres", path);
	auto version = yyjson_obj_get(postgres, "version_num");
	if (!version || !yyjson_is_int(version) || yyjson_get_sint(version) != REQUIRED_POSTGRES_VERSION) {
		ReplayError(path, "postgres.version_num must be exactly 160002");
	}
	artifact.plan_data = RequireStringField(postgres, "plan_data", path);
	const auto sample_family = SamplePlanFamily(artifact.plan_data);
	const auto full_family = FullPlanFamily(artifact.plan_data);
	const auto data_family = full_family.empty() ? sample_family : full_family;
	auto plan_schema_value = yyjson_obj_get(postgres, "plan_schema");
	if (!plan_schema_value) {
		if (artifact.plan_data != "tpch-sf0.01") {
			ReplayError(path, "postgres.plan_schema is required for DuckDB-derived corpus artifacts");
		}
		artifact.plan_schema = "public";
	} else {
		if (!yyjson_is_str(plan_schema_value)) {
			ReplayError(path, "postgres.plan_schema must be a string");
		}
		artifact.plan_schema = string(yyjson_get_str(plan_schema_value), yyjson_get_len(plan_schema_value));
	}
	if (artifact.plan_data == "tpch-sf0.01") {
		if (artifact.plan_schema != "public") {
			ReplayError(path, "postgres.plan_data tpch-sf0.01 requires postgres.plan_schema public");
		}
	} else if (!data_family.empty()) {
		const auto expected_schema = "pgplan_" + data_family;
		if (artifact.plan_schema != expected_schema) {
			ReplayError(path, StringUtil::Format("postgres.plan_data %s requires postgres.plan_schema %s",
			                                     artifact.plan_data, expected_schema));
		}
	} else {
		ReplayError(path,
		            "postgres.plan_data must be tpch-sf0.01, <graph|tpcds|job>-duckdb-sample-<positive>, "
		            "or <tpch|tpcds|job>-duckdb-full");
	}
	auto settings = RequireObjectField(postgres, "settings", path);
	auto parallel_workers = yyjson_obj_get(settings, "max_parallel_workers_per_gather");
	const bool parallel_valid = parallel_workers && yyjson_is_str(parallel_workers) &&
	                            string(yyjson_get_str(parallel_workers), yyjson_get_len(parallel_workers)) == "0";
	if (artifact.plan_schema == "public") {
		if (yyjson_obj_size(settings) != 1 || !parallel_valid) {
			ReplayError(path,
			            "postgres.settings must be exactly {\"max_parallel_workers_per_gather\":\"0\"}");
		}
	} else {
		auto search_path = yyjson_obj_get(settings, "search_path");
		const auto expected_search_path = artifact.plan_schema + ", pg_catalog";
		const bool search_path_valid = search_path && yyjson_is_str(search_path) &&
		                               string(yyjson_get_str(search_path), yyjson_get_len(search_path)) ==
		                                   expected_search_path;
		if (yyjson_obj_size(settings) != 2 || !parallel_valid || !search_path_valid) {
			ReplayError(path,
			            StringUtil::Format("postgres.settings must be exactly max_parallel_workers_per_gather=0 "
			                               "and search_path=%s",
			                               expected_search_path));
		}
	}
	auto tree = yyjson_obj_get(root, "tree");
	if (!tree) {
		ReplayError(path, "missing tree field");
	}
	unordered_set<string> aliases;
	artifact.tree = ParseReplayNode(tree, artifact, aliases, 0);
	ValidateArtifactOccurrences(artifact);
	if (artifact.scan_count == 0 || artifact.join_count + 1 != artifact.scan_count) {
		ReplayError(path, "tree must be a connected binary join tree");
	}
	return artifact;
}

static const LogicalGet &GetReplayTable(const OTNode &node, const string &artifact_path) {
	const auto base = FindBaseOp(node.origin);
	if (!base || base->type != LogicalOperatorType::LOGICAL_GET) {
		ReplayError(artifact_path, "v1 requires every DuckDB leaf to be a base-table scan");
	}
	auto &get = base->Cast<LogicalGet>();
	if (!get.GetTable()) {
		ReplayError(artifact_path, "v1 does not support table-function or replacement scans");
	}
	return get;
}

static void CollectDuckScans(const LogicalOperator &node,
	                         unordered_map<string, vector<const LogicalGet *>> &groups,
	                         unordered_map<idx_t, const LogicalGet *> &gets, const string &artifact_path) {
	if (node.type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = node.Cast<LogicalGet>();
		auto table = get.GetTable();
		if (!table) {
			ReplayError(artifact_path, "v1 does not support table-function or replacement scans");
		}
		if (!gets.emplace(get.table_index.index, &get).second) {
			ReplayError(artifact_path, "DuckDB plan contains a duplicate table index");
		}
		groups[DuckScanSignature(table->ParentSchema().name, table->name)].push_back(&get);
	}
	for (const auto &child : node.children) {
		if (child) {
			CollectDuckScans(*child, groups, gets, artifact_path);
		}
	}
}

static DuckScanInventory BuildDuckScanInventory(const LogicalOperator &plan, const string &artifact_path) {
	DuckScanInventory inventory;
	unordered_map<string, vector<const LogicalGet *>> groups;
	CollectDuckScans(plan, groups, inventory.get_by_table_index, artifact_path);
	for (auto &entry : groups) {
		auto &gets = entry.second;
		std::sort(gets.begin(), gets.end(), [](const LogicalGet *left, const LogicalGet *right) {
			return left->table_index.index < right->table_index.index;
		});
		inventory.count_by_base[entry.first] = gets.size();
		for (idx_t occurrence = 0; occurrence < gets.size(); occurrence++) {
			const auto table_index = gets[occurrence]->table_index.index;
			inventory.occurrence_by_table_index[table_index] = occurrence;
			inventory.table_index_by_identity[ScanOccurrenceSignature(entry.first, occurrence)] = table_index;
		}
	}
	return inventory;
}

static string DuckScanIdentity(const LogicalGet &get,
	                           const unordered_map<idx_t, idx_t> &occurrence_by_table_index,
	                           const string &artifact_path) {
	auto table = get.GetTable();
	if (!table) {
		ReplayError(artifact_path, "final plan contains a non-table scan");
	}
	auto occurrence = occurrence_by_table_index.find(get.table_index.index);
	if (occurrence == occurrence_by_table_index.end()) {
		ReplayError(artifact_path, "final plan contains an unknown table occurrence");
	}
	return ScanOccurrenceSignature(DuckScanSignature(table->ParentSchema().name, table->name), occurrence->second);
}

static string OTScanSignature(const OTNode &node,
	                          const unordered_map<idx_t, idx_t> &occurrence_by_table_index,
	                          const string &artifact_path) {
	return DuckScanIdentity(GetReplayTable(node, artifact_path), occurrence_by_table_index, artifact_path);
}

static TreeSignatures OTSignatures(const OTNode &node,
	                               const unordered_map<idx_t, idx_t> &occurrence_by_table_index,
	                               const string &artifact_path) {
	if (node.kind == OTNode::Kind::RELATION) {
		auto signature = OTScanSignature(node, occurrence_by_table_index, artifact_path);
		return {signature, signature};
	}
	if (!node.info || !node.children[0] || !node.children[1]) {
		ReplayError(artifact_path, "malformed imported OT join node");
	}
	return JoinSignatures(node.info->join_kind,
	                      OTSignatures(*node.children[0], occurrence_by_table_index, artifact_path),
	                      OTSignatures(*node.children[1], occurrence_by_table_index, artifact_path));
}

static void DetachSourceOT(unique_ptr<OTNode> node, vector<unique_ptr<OTNode>> &leaves,
	                       vector<SourceJoin> &joins, const string &artifact_path) {
	if (node->kind == OTNode::Kind::RELATION) {
		if (node->relation_id >= leaves.size() || leaves[node->relation_id]) {
			ReplayError(artifact_path, "DuckDB relation IDs are malformed or duplicated");
		}
		leaves[node->relation_id] = std::move(node);
		return;
	}
	if (!node->info || !node->children[0] || !node->children[1]) {
		ReplayError(artifact_path, "DuckDB OT contains a malformed join");
	}
	SourceJoin source;
	source.info = std::move(node->info);
	auto left = std::move(node->children[0]);
	auto right = std::move(node->children[1]);
	joins.push_back(std::move(source));
	DetachSourceOT(std::move(left), leaves, joins, artifact_path);
	DetachSourceOT(std::move(right), leaves, joins, artifact_path);
}

static void UnionRelations(unordered_set<idx_t> &target, const unordered_set<idx_t> &source) {
	for (auto relation : source) {
		target.insert(relation);
	}
}

static BuiltSubtree BuildImportedSkeleton(const ReplayNode &artifact_node,
	                                      const unordered_map<string, idx_t> &relation_by_identity,
	                                      vector<unique_ptr<OTNode>> &leaves,
	                                      vector<OTNode *> &imported_joins, const string &artifact_path) {
	if (artifact_node.type == ReplayNode::Type::SCAN) {
		auto entry = relation_by_identity.find(ArtifactScanIdentity(artifact_node));
		if (entry == relation_by_identity.end()) {
			ReplayError(artifact_path, "artifact relation is missing from DuckDB query: " + artifact_node.schema + "." +
			                               artifact_node.relation + "#" + to_string(artifact_node.occurrence));
		}
		auto relation_id = entry->second;
		if (relation_id >= leaves.size() || !leaves[relation_id]) {
			ReplayError(artifact_path, "artifact relation matched more than once: " + artifact_node.schema + "." +
			                               artifact_node.relation);
		}
		BuiltSubtree result;
		result.node = std::move(leaves[relation_id]);
		result.relations.insert(relation_id);
		return result;
	}

	auto left = BuildImportedSkeleton(*artifact_node.left, relation_by_identity, leaves, imported_joins,
	                                  artifact_path);
	auto right = BuildImportedSkeleton(*artifact_node.right, relation_by_identity, leaves, imported_joins,
	                                   artifact_path);
	auto join = make_uniq<OTNode>();
	join->kind = OTNode::Kind::JOIN;
	join->info = make_uniq<OTJoin>();
	join->info->join_kind = artifact_node.join_type;
	join->info->original_join_kind = artifact_node.join_type;
	join->children[0] = std::move(left.node);
	join->children[1] = std::move(right.node);
	BuiltSubtree result;
	result.node = std::move(join);
	result.relations = std::move(left.relations);
	UnionRelations(result.relations, right.relations);
	result.node->subtree_relations = result.relations;
	imported_joins.push_back(result.node.get());
	return result;
}

static bool ContainsAll(const unordered_set<idx_t> &container, const unordered_set<idx_t> &values) {
	for (auto value : values) {
		if (!container.count(value)) {
			return false;
		}
	}
	return true;
}

static unordered_set<idx_t> ExpressionRelations(
	const Expression &expression, const unordered_map<idx_t, RelationId> &table_to_relation,
	const string &artifact_path) {
	unordered_set<idx_t> table_indexes;
	OuterYanApplicability::CollectColumnTables(expression, table_indexes);
	unordered_set<idx_t> result;
	for (auto table_index : table_indexes) {
		auto entry = table_to_relation.find(table_index);
		if (entry == table_to_relation.end()) {
			ReplayError(artifact_path, "bound join condition references a relation outside the DuckDB join tree");
		}
		result.insert(entry->second);
	}
	return result;
}

static OTNode *LowestCoveringJoin(OTNode &node, const unordered_set<idx_t> &relations) {
	if (relations.empty() || !ContainsAll(node.subtree_relations, relations) ||
	    node.kind == OTNode::Kind::RELATION) {
		return nullptr;
	}
	for (idx_t side = 0; side < 2; side++) {
		auto &child = *node.children[side];
		if (ContainsAll(child.subtree_relations, relations)) {
			return LowestCoveringJoin(child, relations);
		}
	}
	return &node;
}

static OTNode *AnchorTarget(OTNode &root, const OTJoin &source, const string &artifact_path) {
	unordered_set<idx_t> anchor_relations {source.cond_left_relation_id, source.cond_right_relation_id};
	auto target = LowestCoveringJoin(root, anchor_relations);
	if (!target) {
		ReplayError(artifact_path, "original DuckDB equality anchor does not map to an imported join node");
	}
	return target;
}

static void AddConditionToImportedJoin(OTNode &target, const JoinCondition &source_condition,
	                                   const unordered_map<idx_t, RelationId> &table_to_relation,
	                                   const string &artifact_path) {
	auto condition = source_condition.Copy();
	if (!condition.IsComparison()) {
		auto relations = ExpressionRelations(condition.GetJoinExpression(), table_to_relation, artifact_path);
		if (!ContainsAll(target.subtree_relations, relations)) {
			ReplayError(artifact_path, "bound join residual falls outside its imported ON subtree");
		}
		target.info->conditions.push_back(std::move(condition));
		return;
	}
	auto lhs_relations = ExpressionRelations(condition.GetLHS(), table_to_relation, artifact_path);
	auto rhs_relations = ExpressionRelations(condition.GetRHS(), table_to_relation, artifact_path);
	if (!ContainsAll(target.subtree_relations, lhs_relations) ||
	    !ContainsAll(target.subtree_relations, rhs_relations)) {
		ReplayError(artifact_path, "bound join comparison falls outside its imported ON subtree");
	}
	const bool aligned = !lhs_relations.empty() && !rhs_relations.empty() &&
	                     ContainsAll(target.children[0]->subtree_relations, lhs_relations) &&
	                     ContainsAll(target.children[1]->subtree_relations, rhs_relations);
	const bool reversed = !lhs_relations.empty() && !rhs_relations.empty() &&
	                      ContainsAll(target.children[1]->subtree_relations, lhs_relations) &&
	                      ContainsAll(target.children[0]->subtree_relations, rhs_relations);
	if (reversed && !aligned) {
		condition.Swap();
		target.info->conditions.push_back(std::move(condition));
		return;
	}
	if (aligned) {
		target.info->conditions.push_back(std::move(condition));
		return;
	}
	// A stable INNER predicate can acquire a different lowest covering split
	// after regrouping. Preserve it as one arbitrary bound ON expression when
	// neither comparison side belongs wholly to one physical child.
	auto expression = JoinCondition::CreateExpression(std::move(condition));
	target.info->conditions.emplace_back(std::move(expression));
}

static void ValidateAndAttachOuterJoin(const SourceJoin &source, OTNode &root,
	                                   unordered_set<OTNode *> &claimed_outer_nodes,
	                                   const unordered_map<idx_t, RelationId> &table_to_relation,
	                                   const string &artifact_path) {
	auto &info = *source.info;
	auto target = AnchorTarget(root, info, artifact_path);
	const bool lhs_left = target->children[0]->subtree_relations.count(info.cond_left_relation_id) != 0;
	const bool rhs_right = target->children[1]->subtree_relations.count(info.cond_right_relation_id) != 0;
	const bool lhs_right = target->children[1]->subtree_relations.count(info.cond_left_relation_id) != 0;
	const bool rhs_left = target->children[0]->subtree_relations.count(info.cond_right_relation_id) != 0;
	if (!((lhs_left && rhs_right) || (lhs_right && rhs_left))) {
		ReplayError(artifact_path,
		            "join type/preserved-side mismatch: imported outer equality does not span its children");
	}
	auto expected_kind = lhs_left ? info.join_kind : FlipOuterYanJoinKind(info.join_kind);
	if (target->info->join_kind != expected_kind) {
		ReplayError(artifact_path,
		            StringUtil::Format("join type/preserved-side mismatch: PostgreSQL has %s but DuckDB's "
		                               "independent null-rejection analysis permits %s",
		                               JoinToken(target->info->join_kind), JoinToken(expected_kind)));
	}
	if (!claimed_outer_nodes.insert(target).second) {
		ReplayError(artifact_path,
		            "imported split has no matching one-to-one outer join edge (multiple source edges map here)");
	}
	for (const auto &condition : info.conditions) {
		AddConditionToImportedJoin(*target, condition, table_to_relation, artifact_path);
	}
}

struct EqualityColumn {
	const BoundColumnRefExpression *expression;
	idx_t relation;
};

class EqualityClasses {
public:
	void Add(const BoundColumnRefExpression &left, idx_t left_relation,
	         const BoundColumnRefExpression &right, idx_t right_relation) {
		auto left_id = Register(left, left_relation);
		auto right_id = Register(right, right_relation);
		Union(left_id, right_id);
	}

	bool AddImpliedEquality(OTNode &target) {
		for (idx_t left = 0; left < columns.size(); left++) {
			if (!target.children[0]->subtree_relations.count(columns[left].relation)) {
				continue;
			}
			for (idx_t right = 0; right < columns.size(); right++) {
				if (!target.children[1]->subtree_relations.count(columns[right].relation) ||
				    Find(left) != Find(right)) {
					continue;
				}
				target.info->conditions.emplace_back(columns[left].expression->Copy(),
				                                           columns[right].expression->Copy(),
				                                           ExpressionType::COMPARE_EQUAL);
				return true;
			}
		}
		return false;
	}

private:
	idx_t Register(const BoundColumnRefExpression &expression, idx_t relation) {
		auto entry = binding_to_id.find(expression.binding);
		if (entry != binding_to_id.end()) {
			return entry->second;
		}
		auto id = columns.size();
		binding_to_id.emplace(expression.binding, id);
		columns.push_back({&expression, relation});
		parents.push_back(id);
		return id;
	}

	idx_t Find(idx_t id) {
		while (parents[id] != id) {
			parents[id] = parents[parents[id]];
			id = parents[id];
		}
		return id;
	}

	void Union(idx_t left, idx_t right) {
		left = Find(left);
		right = Find(right);
		if (left != right) {
			parents[right] = left;
		}
	}

	column_binding_map_t<idx_t> binding_to_id;
	vector<EqualityColumn> columns;
	vector<idx_t> parents;
};

static bool FindEqualityAnchor(OTNode &join,
	                           const unordered_map<idx_t, RelationId> &table_to_relation,
	                           idx_t &anchor_index, idx_t &left_relation, idx_t &right_relation,
	                           const string &artifact_path) {
	for (idx_t condition_index = 0; condition_index < join.info->conditions.size(); condition_index++) {
		auto &condition = join.info->conditions[condition_index];
		if (!condition.IsComparison() || condition.GetComparisonType() != ExpressionType::COMPARE_EQUAL) {
			continue;
		}
		auto lhs = ExpressionRelations(condition.GetLHS(), table_to_relation, artifact_path);
		auto rhs = ExpressionRelations(condition.GetRHS(), table_to_relation, artifact_path);
		if (lhs.size() != 1 || rhs.size() != 1) {
			continue;
		}
		const auto lhs_relation = *lhs.begin();
		const auto rhs_relation = *rhs.begin();
		if (join.children[0]->subtree_relations.count(lhs_relation) &&
		    join.children[1]->subtree_relations.count(rhs_relation)) {
			anchor_index = condition_index;
			left_relation = lhs_relation;
			right_relation = rhs_relation;
			return true;
		}
		if (join.children[1]->subtree_relations.count(lhs_relation) &&
		    join.children[0]->subtree_relations.count(rhs_relation)) {
			condition.Swap();
			anchor_index = condition_index;
			left_relation = rhs_relation;
			right_relation = lhs_relation;
			return true;
		}
	}
	return false;
}

static idx_t AttachSourceConditionsAndValidateKinds(
	OTNode &root, const vector<SourceJoin> &source_joins, const vector<OTNode *> &imported_joins,
	const unordered_map<idx_t, RelationId> &table_to_relation, const string &artifact_path) {
	unordered_set<OTNode *> claimed_outer_nodes;
	for (const auto &source : source_joins) {
		if (source.info->join_kind != JoinType::INNER) {
			ValidateAndAttachOuterJoin(source, root, claimed_outer_nodes, table_to_relation, artifact_path);
		}
	}
	for (auto imported : imported_joins) {
		if (imported->info->join_kind != JoinType::INNER && !claimed_outer_nodes.count(imported)) {
			ReplayError(artifact_path,
			            "join type/preserved-side mismatch: PostgreSQL retains an unproven outer join");
		}
	}

	EqualityClasses equalities;
	for (const auto &source : source_joins) {
		if (source.info->join_kind != JoinType::INNER) {
			continue;
		}
		auto anchor_target = AnchorTarget(root, *source.info, artifact_path);
		for (const auto &condition : source.info->conditions) {
			OTNode *target = anchor_target;
			if (condition.IsComparison()) {
				auto relations = ExpressionRelations(condition.GetLHS(), table_to_relation, artifact_path);
				auto rhs = ExpressionRelations(condition.GetRHS(), table_to_relation, artifact_path);
				UnionRelations(relations, rhs);
				if (auto lowest = LowestCoveringJoin(root, relations)) {
					target = lowest;
				}
			} else {
				auto relations =
				    ExpressionRelations(condition.GetJoinExpression(), table_to_relation, artifact_path);
				relations.insert(source.info->cond_left_relation_id);
				relations.insert(source.info->cond_right_relation_id);
				if (auto lowest = LowestCoveringJoin(root, relations)) {
					target = lowest;
				}
			}
			if (target->info->join_kind != JoinType::INNER) {
				ReplayError(artifact_path,
				            "an INNER DuckDB predicate would move into an imported outer-join ON scope");
			}
			AddConditionToImportedJoin(*target, condition, table_to_relation, artifact_path);

			if (condition.IsComparison() && condition.GetComparisonType() == ExpressionType::COMPARE_EQUAL &&
			    condition.GetLHS().GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF &&
			    condition.GetRHS().GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
				auto &left = condition.GetLHS().Cast<BoundColumnRefExpression>();
				auto &right = condition.GetRHS().Cast<BoundColumnRefExpression>();
				auto left_relation = table_to_relation.find(left.binding.table_index.index);
				auto right_relation = table_to_relation.find(right.binding.table_index.index);
				if (left_relation != table_to_relation.end() && right_relation != table_to_relation.end()) {
					equalities.Add(left, left_relation->second, right, right_relation->second);
				}
			}
		}
	}

	idx_t implied_equalities = 0;
	for (auto imported : imported_joins) {
		idx_t anchor_index = 0;
		idx_t left_relation = DConstants::INVALID_INDEX;
		idx_t right_relation = DConstants::INVALID_INDEX;
		if (!FindEqualityAnchor(*imported, table_to_relation, anchor_index, left_relation, right_relation,
		                        artifact_path)) {
			if (imported->info->join_kind != JoinType::INNER || !equalities.AddImpliedEquality(*imported) ||
			    !FindEqualityAnchor(*imported, table_to_relation, anchor_index, left_relation, right_relation,
			                        artifact_path)) {
				ReplayError(artifact_path,
				            "imported split has no matching original or independently implied equality edge");
			}
			implied_equalities++;
		}
		if (anchor_index != 0) {
			std::swap(imported->info->conditions[0], imported->info->conditions[anchor_index]);
		}
		imported->info->cond_left_relation_id = left_relation;
		imported->info->cond_right_relation_id = right_relation;
	}
	return implied_equalities;
}

static void RefreshOTIndexes(OTNode &node, vector<OTNode *> &relations, vector<OTNode *> &joins,
	                         const string &artifact_path) {
	if (node.kind == OTNode::Kind::RELATION) {
		if (node.relation_id >= relations.size() || relations[node.relation_id]) {
			ReplayError(artifact_path, "rebuilt OT contains a duplicate relation ID");
		}
		relations[node.relation_id] = &node;
		return;
	}
	RefreshOTIndexes(*node.children[0], relations, joins, artifact_path);
	RefreshOTIndexes(*node.children[1], relations, joins, artifact_path);
	node.order = joins.size() + 1;
	joins.push_back(&node);
}

static bool ImportedTreeContainsFilterScope(const OTNode &node,
	                                        const unordered_set<idx_t> &evaluation_relations) {
	if (node.subtree_relations == evaluation_relations) {
		return true;
	}
	if (node.kind == OTNode::Kind::RELATION) {
		return false;
	}
	return ImportedTreeContainsFilterScope(*node.children[0], evaluation_relations) ||
	       ImportedTreeContainsFilterScope(*node.children[1], evaluation_relations);
}

static void ValidateSensitiveFilterScopes(OuterYanTree &tree, const string &artifact_path) {
	for (const auto &record : tree.filter_records) {
		if (!record || !record->filter || !record->requires_original_scope) {
			continue;
		}
		if (!ImportedTreeContainsFilterScope(tree.OT().Root(), record->evaluation_relations)) {
			ReplayError(artifact_path,
			            StringUtil::Format("imported tree cannot preserve evaluation scope for volatile or "
			                               "potentially throwing filter %llu (%llu input relations)",
			                               record->filter_index, record->evaluation_relations.size()));
		}
	}
}

static TreeSignatures LogicalPlanSignatures(const LogicalOperator &node,
	                                        const unordered_map<idx_t, idx_t> &occurrence_by_table_index,
	                                        const string &artifact_path) {
	if (node.type == LogicalOperatorType::LOGICAL_GET) {
		auto signature = DuckScanIdentity(node.Cast<LogicalGet>(), occurrence_by_table_index, artifact_path);
		return {signature, signature};
	}
	if (node.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		if (node.children.size() != 2 || !node.children[0] || !node.children[1]) {
			throw InvalidInputException("[PGPLAN] final plan contains a malformed comparison join");
		}
		auto &join = node.Cast<LogicalComparisonJoin>();
		return JoinSignatures(join.join_type,
		                      LogicalPlanSignatures(*node.children[0], occurrence_by_table_index, artifact_path),
		                      LogicalPlanSignatures(*node.children[1], occurrence_by_table_index, artifact_path));
	}
	if (node.children.size() == 1 && node.children[0]) {
		return LogicalPlanSignatures(*node.children[0], occurrence_by_table_index, artifact_path);
	}
	throw InvalidInputException("[PGPLAN] final plan contains unsupported operator %s",
	                            EnumUtil::ToString(node.type));
}

struct EliminationCandidate {
	LogicalComparisonJoin *join;
	idx_t omitted_child;
	idx_t omitted_table_index;
};

static void CollectSubtreeTableIndexes(const LogicalOperator &node, unordered_set<idx_t> &table_indexes) {
	for (const auto &table_index : node.GetTableIndex()) {
		table_indexes.insert(table_index.index);
	}
	for (const auto &child : node.children) {
		if (child) {
			CollectSubtreeTableIndexes(*child, table_indexes);
		}
	}
}

static bool StableExpressions(LogicalOperator &node, const unordered_set<idx_t> &allowed_table_indexes) {
	bool valid = true;
	LogicalOperatorVisitor::EnumerateExpressions(node, [&](unique_ptr<Expression> *expression) {
		if (!valid || !expression || !*expression || (*expression)->IsVolatile() || (*expression)->CanThrow()) {
			valid = false;
			return;
		}
		unordered_set<idx_t> referenced;
		OuterYanApplicability::CollectColumnTables(**expression, referenced);
		for (auto table_index : referenced) {
			if (!allowed_table_indexes.count(table_index)) {
				valid = false;
				return;
			}
		}
	});
	if (!valid) {
		return false;
	}
	for (auto &child : node.children) {
		if (child && !StableExpressions(*child, allowed_table_indexes)) {
			return false;
		}
	}
	return valid;
}

static LogicalGet *FindSimpleBaseScan(LogicalOperator &node) {
	switch (node.type) {
	case LogicalOperatorType::LOGICAL_GET:
		return &node.Cast<LogicalGet>();
	case LogicalOperatorType::LOGICAL_FILTER:
	case LogicalOperatorType::LOGICAL_PROJECTION:
		if (node.children.size() == 1 && node.children[0]) {
			return FindSimpleBaseScan(*node.children[0]);
		}
		return nullptr;
	default:
		return nullptr;
	}
}

static bool ResolveToBaseColumn(const LogicalOperator &node, ColumnBinding binding, const LogicalGet &base_get,
	                            idx_t &table_column) {
	switch (node.type) {
	case LogicalOperatorType::LOGICAL_FILTER:
		return node.children.size() == 1 && node.children[0] &&
		       ResolveToBaseColumn(*node.children[0], binding, base_get, table_column);
	case LogicalOperatorType::LOGICAL_PROJECTION: {
		auto &projection = node.Cast<LogicalProjection>();
		if (binding.table_index != projection.table_index) {
			return false;
		}
		const auto projection_index = binding.column_index.GetIndexUnsafe();
		if (projection_index >= projection.expressions.size() ||
		    projection.expressions[projection_index]->GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
			return false;
		}
		auto child_binding =
		    projection.expressions[projection_index]->Cast<BoundColumnRefExpression>().binding;
		return node.children.size() == 1 && node.children[0] &&
		       ResolveToBaseColumn(*node.children[0], child_binding, base_get, table_column);
	}
	case LogicalOperatorType::LOGICAL_GET: {
		auto &get = node.Cast<LogicalGet>();
		if (&get != &base_get || binding.table_index != get.table_index) {
			return false;
		}
		const auto projection_index = binding.column_index.GetIndexUnsafe();
		const auto &column_ids = get.GetColumnIds();
		if (projection_index >= column_ids.size()) {
			return false;
		}
		const auto &column_id = column_ids[projection_index];
		if (!column_id.HasPrimaryIndex() || column_id.IsVirtualColumn() || column_id.HasChildren()) {
			return false;
		}
		table_column = column_id.GetPrimaryIndex();
		return true;
	}
	default:
		return false;
	}
}

static bool JoinKeysProveUnique(LogicalComparisonJoin &join, LogicalOperator &omitted_subtree,
	                            LogicalGet &omitted_get,
	                            const unordered_set<idx_t> &omitted_table_indexes) {
	auto table = omitted_get.GetTable();
	if (!table || omitted_get.table_filters.HasFilters()) {
		return false;
	}
	vector<idx_t> key_columns;
	for (const auto &condition : join.conditions) {
		if (condition.IsComparison()) {
			if (condition.GetLHS().IsVolatile() || condition.GetLHS().CanThrow() ||
			    condition.GetRHS().IsVolatile() || condition.GetRHS().CanThrow()) {
				return false;
			}
		} else {
			const auto &expression = condition.GetJoinExpression();
			if (expression.IsVolatile() || expression.CanThrow()) {
				return false;
			}
		}
		if (!condition.IsComparison() || condition.GetComparisonType() != ExpressionType::COMPARE_EQUAL ||
		    condition.GetLHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF ||
		    condition.GetRHS().GetExpressionClass() != ExpressionClass::BOUND_COLUMN_REF) {
			continue;
		}
		const auto lhs_binding = condition.GetLHS().Cast<BoundColumnRefExpression>().binding;
		const auto rhs_binding = condition.GetRHS().Cast<BoundColumnRefExpression>().binding;
		const bool lhs_omitted = omitted_table_indexes.count(lhs_binding.table_index.index) != 0;
		const bool rhs_omitted = omitted_table_indexes.count(rhs_binding.table_index.index) != 0;
		if (lhs_omitted == rhs_omitted) {
			continue;
		}
		const auto omitted_binding = lhs_omitted ? lhs_binding : rhs_binding;
		idx_t table_column;
		if (ResolveToBaseColumn(omitted_subtree, omitted_binding, omitted_get, table_column)) {
			key_columns.push_back(table_column);
		}
	}
	if (key_columns.empty()) {
		return false;
	}
	auto has_column = [&](idx_t table_column) {
		return std::find(key_columns.begin(), key_columns.end(), table_column) != key_columns.end();
	};
	auto has_name = [&](const string &name) {
		for (auto table_column : key_columns) {
			if (table_column < omitted_get.names.size() &&
			    StringUtil::CIEquals(omitted_get.names[table_column], name)) {
				return true;
			}
		}
		return false;
	};
	for (const auto &constraint : table->GetConstraints()) {
		if (constraint->type != ConstraintType::UNIQUE) {
			continue;
		}
		auto &unique = constraint->Cast<UniqueConstraint>();
		if (unique.index.index != DConstants::INVALID_INDEX) {
			if (has_column(unique.index.index)) {
				return true;
			}
			continue;
		}
		if (unique.columns.empty()) {
			continue;
		}
		bool all_present = true;
		for (const auto &column : unique.columns) {
			if (!has_name(column)) {
				all_present = false;
				break;
			}
		}
		if (all_present) {
			return true;
		}
	}
	return false;
}

static bool ReferencesOmittedOutsideTarget(LogicalOperator &node, const LogicalOperator &target_join,
	                                       const LogicalOperator &omitted_subtree,
	                                       const unordered_set<idx_t> &omitted_table_indexes) {
	if (&node == &omitted_subtree) {
		return false;
	}
	if (&node != &target_join) {
		bool referenced = false;
		LogicalOperatorVisitor::EnumerateExpressions(node, [&](unique_ptr<Expression> *expression) {
			if (referenced || !expression || !*expression) {
				return;
			}
			unordered_set<idx_t> table_indexes;
			OuterYanApplicability::CollectColumnTables(**expression, table_indexes);
			for (auto table_index : table_indexes) {
				if (omitted_table_indexes.count(table_index)) {
					referenced = true;
					return;
				}
			}
		});
		if (referenced) {
			return true;
		}
	}
	for (auto &child : node.children) {
		if (child && ReferencesOmittedOutsideTarget(*child, target_join, omitted_subtree,
		                                             omitted_table_indexes)) {
			return true;
		}
	}
	return false;
}

static void FindEliminationCandidates(LogicalOperator &node, LogicalOperator &plan_root,
	                                  const unordered_set<idx_t> &omitted,
	                                  unordered_map<idx_t, EliminationCandidate> &candidates,
	                                  const string &artifact_path) {
	if (node.type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		auto &join = node.Cast<LogicalComparisonJoin>();
		optional_idx omitted_child;
		if (join.join_type == JoinType::LEFT) {
			omitted_child = optional_idx(1);
		} else if (join.join_type == JoinType::RIGHT) {
			omitted_child = optional_idx(0);
		}
		if (omitted_child.IsValid() && join.children.size() == 2 && join.children[omitted_child.GetIndex()]) {
			auto &subtree = *join.children[omitted_child.GetIndex()];
			auto base_get = FindSimpleBaseScan(subtree);
			if (base_get && omitted.count(base_get->table_index.index)) {
				unordered_set<idx_t> subtree_indexes;
				CollectSubtreeTableIndexes(subtree, subtree_indexes);
				bool output_visible = false;
				for (const auto &binding : plan_root.GetColumnBindings()) {
					if (subtree_indexes.count(binding.table_index.index)) {
						output_visible = true;
						break;
					}
				}
				if (output_visible || !StableExpressions(subtree, subtree_indexes) ||
				    !JoinKeysProveUnique(join, subtree, *base_get, subtree_indexes) ||
				    ReferencesOmittedOutsideTarget(plan_root, join, subtree, subtree_indexes)) {
					ReplayError(artifact_path,
					            "PostgreSQL omitted a DuckDB outer-join side that is not independently eliminable");
				}
				if (!candidates.emplace(base_get->table_index.index,
				                        EliminationCandidate {&join, omitted_child.GetIndex(),
				                                              base_get->table_index.index})
				         .second) {
					ReplayError(artifact_path, "an omitted DuckDB scan matches multiple outer-join eliminations");
				}
			}
		}
	}
	for (auto &child : node.children) {
		if (child) {
			FindEliminationCandidates(*child, plan_root, omitted, candidates, artifact_path);
		}
	}
}

static unique_ptr<LogicalOperator> PruneEliminatedJoins(
	unique_ptr<LogicalOperator> node,
	const unordered_map<const LogicalComparisonJoin *, EliminationCandidate> &candidate_by_join) {
	if (!node) {
		return node;
	}
	if (node->type == LogicalOperatorType::LOGICAL_COMPARISON_JOIN) {
		auto &join = node->Cast<LogicalComparisonJoin>();
		auto candidate = candidate_by_join.find(&join);
		if (candidate != candidate_by_join.end()) {
			auto preserved_child = 1 - candidate->second.omitted_child;
			return PruneEliminatedJoins(std::move(join.children[preserved_child]), candidate_by_join);
		}
	}
	for (auto &child : node->children) {
		child = PruneEliminatedJoins(std::move(child), candidate_by_join);
	}
	return node;
}

static unordered_set<idx_t> MatchArtifactScans(const ReplayArtifact &artifact,
	                                           const DuckScanInventory &inventory) {
	unordered_set<idx_t> retained;
	for (const auto scan : artifact.scans) {
		auto match = inventory.table_index_by_identity.find(ArtifactScanIdentity(*scan));
		if (match == inventory.table_index_by_identity.end()) {
			ReplayError(artifact.path, "artifact relation occurrence is missing from DuckDB query: " + scan->schema +
			                               "." + scan->relation + "#" + to_string(scan->occurrence));
		}
		if (!retained.insert(match->second).second) {
			ReplayError(artifact.path, "artifact relation occurrence matched DuckDB more than once");
		}
	}
	return retained;
}

static void ApplyProvenOuterJoinElimination(unique_ptr<LogicalOperator> &plan, const ReplayArtifact &artifact,
	                                        const DuckScanInventory &inventory) {
	auto retained = MatchArtifactScans(artifact, inventory);
	unordered_set<idx_t> omitted;
	for (const auto &entry : inventory.get_by_table_index) {
		if (!retained.count(entry.first)) {
			omitted.insert(entry.first);
		}
	}
	if (omitted.empty()) {
		return;
	}
	unordered_map<idx_t, EliminationCandidate> candidates;
	FindEliminationCandidates(*plan, *plan, omitted, candidates, artifact.path);
	for (auto table_index : omitted) {
		if (!candidates.count(table_index)) {
			ReplayError(artifact.path,
			            "PostgreSQL artifact omits a DuckDB scan without an independently proven outer-join elimination");
		}
	}
	unordered_map<const LogicalComparisonJoin *, EliminationCandidate> candidate_by_join;
	for (const auto &entry : candidates) {
		if (!candidate_by_join.emplace(entry.second.join, entry.second).second) {
			ReplayError(artifact.path, "one DuckDB outer join cannot eliminate more than one artifact subtree");
		}
	}
	plan = PruneEliminatedJoins(std::move(plan), candidate_by_join);
	plan->ResolveOperatorTypes();
}

} // namespace

PostgresPlanReplay::PostgresPlanReplay(ClientContext &context_p) : context(context_p) {
}

optional<string> PostgresPlanReplay::ConfiguredPlanPath(ClientContext &context) {
	auto &config = ClientConfig::GetConfig(context);
	auto entry = config.user_variables.find(VARIABLE_NAME);
	if (entry == config.user_variables.end()) {
		entry = config.user_variables.find(LEGACY_VARIABLE_NAME);
		if (entry == config.user_variables.end()) {
			return optional<string>();
		}
	} else if (config.user_variables.find(LEGACY_VARIABLE_NAME) != config.user_variables.end()) {
		throw InvalidInputException(
		    "[PGPLAN] SET VARIABLE %s and compatibility alias %s cannot both be set; RESET one of them",
		    VARIABLE_NAME, LEGACY_VARIABLE_NAME);
	}
	const auto &variable_name = entry->first;
	if (entry->second.IsNull()) {
		throw InvalidInputException("[PGPLAN] SET VARIABLE %s must be a non-NULL absolute path", variable_name);
	}
	if (entry->second.type().id() != LogicalTypeId::VARCHAR) {
		throw InvalidInputException("[PGPLAN] SET VARIABLE %s must be a VARCHAR absolute path (got %s)", variable_name,
		                            entry->second.type().ToString());
	}
	auto path = entry->second.GetValue<string>();
	if (path.empty()) {
		throw InvalidInputException("[PGPLAN] SET VARIABLE %s must not be empty", variable_name);
	}
	auto &fs = FileSystem::GetFileSystem(context);
	if (!fs.IsPathAbsolute(path)) {
		throw InvalidInputException("[PGPLAN] SET VARIABLE %s must be an absolute path (got %s)", variable_name,
		                            path.c_str());
	}
	return path;
}

PostgresPlanReplayResult PostgresPlanReplay::Apply(unique_ptr<LogicalOperator> input) {
	if (!input) {
		throw InternalException("PostgresPlanReplay::Apply: null input plan");
	}
	auto configured_path = ConfiguredPlanPath(context);
	if (!configured_path) {
		throw InternalException("PostgresPlanReplay::Apply called without an active PGPlan variable");
	}
	auto artifact = ReadArtifact(context, *configured_path);

	const bool is_explain = input->type == LogicalOperatorType::LOGICAL_EXPLAIN;
	string query_to_verify = context.GetCurrentQuery();
	if (is_explain) {
		auto &explain = input->Cast<LogicalExplain>();
		if (explain.explain_type == ExplainType::EXPLAIN_ANALYZE) {
			ReplayError(artifact.path,
			            "EXPLAIN ANALYZE is unsupported because PGPlan requires bare-query hash verification");
		}
		query_to_verify = ExtractPlainExplainInnerQuery(query_to_verify, artifact.path);
	}
	auto actual_query_sha256 = QuerySHA256(query_to_verify);
	if (actual_query_sha256 != artifact.query_sha256) {
		ReplayError(artifact.path,
		            StringUtil::Format("query_sha256 mismatch (artifact=%s, DuckDB=%s)",
		                               artifact.query_sha256, actual_query_sha256));
	}

	unique_ptr<LogicalOperator> explain_wrapper;
	unique_ptr<LogicalOperator> working_plan;
	if (is_explain) {
		if (input->children.size() != 1 || !input->children[0]) {
			ReplayError(artifact.path, "malformed LogicalExplain wrapper");
		}
		explain_wrapper = std::move(input);
		working_plan = std::move(explain_wrapper->children[0]);
	} else {
		working_plan = std::move(input);
	}
	auto scan_inventory = BuildDuckScanInventory(*working_plan, artifact.path);
	for (const auto scan : artifact.scans) {
		const auto base = ArtifactScanSignature(scan->schema, scan->relation);
		auto count = scan_inventory.count_by_base.find(base);
		if (!scan->has_occurrence &&
		    (count == scan_inventory.count_by_base.end() || count->second != 1)) {
			ReplayError(artifact.path,
			            "legacy scan without occurrence can match only a unique DuckDB base relation: " +
			                scan->schema + "." + scan->relation);
		}
	}
	ApplyProvenOuterJoinElimination(working_plan, artifact, scan_inventory);
	auto remaining_inventory = BuildDuckScanInventory(*working_plan, artifact.path);
	if (remaining_inventory.get_by_table_index.size() != artifact.scan_count) {
		ReplayError(artifact.path,
		            StringUtil::Format("artifact/query size mismatch after proven join elimination "
		                               "(artifact=%llu scans, DuckDB=%llu scans)",
		                               artifact.scan_count, remaining_inventory.get_by_table_index.size()));
	}

	if (artifact.join_count == 0) {
		auto artifact_signatures = ArtifactSignatures(*artifact.tree);
		auto imported_signatures =
		    LogicalPlanSignatures(*working_plan, scan_inventory.occurrence_by_table_index, artifact.path);
		if (artifact_signatures.raw != imported_signatures.raw ||
		    artifact_signatures.semantic != imported_signatures.semantic) {
			ReplayError(artifact.path, "pruned one-leaf DuckDB plan differs from the PostgreSQL artifact");
		}
		auto pgplan = std::move(working_plan);
		if (explain_wrapper) {
			explain_wrapper->children[0] = std::move(pgplan);
			pgplan = std::move(explain_wrapper);
		}
		Printer::Print("[PGPLAN] {\"event\":\"imported\",\"artifact\":" + JSONQuote(artifact.path) +
		               ",\"query_sha256\":" + JSONQuote(artifact.query_sha256) +
		               ",\"query_sha256_verified\":true,\"query_sha256_unverified_reason\":null" +
		               ",\"plan_data\":" + JSONQuote(artifact.plan_data) +
		               ",\"plan_schema\":" + JSONQuote(artifact.plan_schema) +
		               ",\"artifact_raw_signature\":" + JSONQuote(artifact_signatures.raw) +
		               ",\"imported_raw_signature\":" + JSONQuote(imported_signatures.raw) +
		               ",\"expected_semantic_signature\":" + JSONQuote(artifact_signatures.semantic) + "}");
		PostgresPlanReplayResult result;
		result.plan = std::move(pgplan);
		result.artifact_path = artifact.path;
		result.query_sha256 = artifact.query_sha256;
		result.artifact_raw_signature = artifact_signatures.raw;
		result.expected_semantic_signature = artifact_signatures.semantic;
		result.occurrence_by_table_index = std::move(scan_inventory.occurrence_by_table_index);
		return result;
	}

	OuterYanTree replay_tree;
	if (!replay_tree.CheckPGPlanApplicability(*working_plan)) {
		ReplayError(artifact.path, "query is outside PGPlan v1 scope: " + replay_tree.Applicability().reason);
	}
	replay_tree.BuildOT(std::move(working_plan));
	// This is the sole authority for accepting PostgreSQL outer-to-inner
	// reductions; PostgreSQL predicate text is never parsed or rebound.
	Simplification().Apply(replay_tree, /*allow_scan_filter_seeding=*/false);

	const auto relation_count = replay_tree.ot_relations_by_id.size();
	if (artifact.scan_count != relation_count || artifact.join_count != replay_tree.ot_joins_by_order.size()) {
		ReplayError(artifact.path,
		            StringUtil::Format("artifact/query size mismatch (artifact=%llu scans/%llu joins, "
		                               "DuckDB=%llu scans/%llu joins)",
		                               artifact.scan_count, artifact.join_count, relation_count,
		                               replay_tree.ot_joins_by_order.size()));
	}

	unordered_map<string, idx_t> relation_by_identity;
	for (idx_t relation_id = 0; relation_id < relation_count; relation_id++) {
		auto node = replay_tree.ot_relations_by_id[relation_id];
		if (!node) {
			ReplayError(artifact.path, "DuckDB OT has a missing relation node");
		}
		auto &get = GetReplayTable(*node, artifact.path);
		auto table = get.GetTable();
		auto relation_name = table->ParentSchema().name + "." + table->name;
		auto occurrence = scan_inventory.occurrence_by_table_index.find(get.table_index.index);
		if (occurrence == scan_inventory.occurrence_by_table_index.end()) {
			ReplayError(artifact.path, "DuckDB scan is missing its source occurrence: " + relation_name);
		}
		auto key = ScanOccurrenceSignature(DuckScanSignature(table->ParentSchema().name, table->name),
		                                   occurrence->second);
		if (!relation_by_identity.emplace(key, relation_id).second) {
			ReplayError(artifact.path, "DuckDB has a duplicate relation occurrence: " + relation_name + "#" +
			                               to_string(occurrence->second));
		}
	}

	vector<unique_ptr<OTNode>> leaves(relation_count);
	vector<SourceJoin> source_joins;
	source_joins.reserve(replay_tree.ot_joins_by_order.size());
	DetachSourceOT(std::move(replay_tree.OT().root), leaves, source_joins, artifact.path);
	vector<OTNode *> imported_joins;
	imported_joins.reserve(artifact.join_count);
	auto rebuilt = BuildImportedSkeleton(*artifact.tree, relation_by_identity, leaves, imported_joins,
	                                     artifact.path);
	for (const auto &leaf : leaves) {
		if (leaf) {
			ReplayError(artifact.path, "artifact did not consume every DuckDB relation");
		}
	}
	replay_tree.OT().root = std::move(rebuilt.node);
	auto implied_equality_count = AttachSourceConditionsAndValidateKinds(
	    replay_tree.OT().Root(), source_joins, imported_joins, replay_tree.table_to_relation, artifact.path);
	replay_tree.OT().Finalize();
	string validity_reason;
	if (!replay_tree.OT().IsValid(&validity_reason)) {
		ReplayError(artifact.path, "rebuilt OT is invalid: " + validity_reason);
	}
	ValidateSensitiveFilterScopes(replay_tree, artifact.path);
	replay_tree.ot_relations_by_id.assign(relation_count, nullptr);
	replay_tree.ot_joins_by_order.clear();
	RefreshOTIndexes(replay_tree.OT().Root(), replay_tree.ot_relations_by_id,
	                 replay_tree.ot_joins_by_order, artifact.path);

	auto artifact_signatures = ArtifactSignatures(*artifact.tree);
	auto imported_signatures =
	    OTSignatures(replay_tree.OT().Root(), scan_inventory.occurrence_by_table_index, artifact.path);
	if (artifact_signatures.raw != imported_signatures.raw) {
		ReplayError(artifact.path, "rebuilt OT raw signature differs from the PostgreSQL artifact");
	}
	if (artifact_signatures.semantic != imported_signatures.semantic) {
		ReplayError(artifact.path, "rebuilt OT semantic signature differs from the PostgreSQL artifact");
	}

	// Exact logical child orientation is retained by lowering the validated OT
	// directly. OJT construction is intentionally skipped because PGPlan keeps
	// stable non-equality/non-comparison ON residuals that OJT does not model.
	auto replayed_plan = replay_tree.OTToLogicalPlanPreservingShape(context);
	if (explain_wrapper) {
		explain_wrapper->children[0] = std::move(replayed_plan);
		replayed_plan = std::move(explain_wrapper);
	}
	auto replayed_signatures =
	    LogicalPlanSignatures(*replayed_plan, scan_inventory.occurrence_by_table_index, artifact.path);
	if (replayed_signatures.raw != artifact_signatures.raw) {
		ReplayError(artifact.path, "lowered DuckDB logical tree changed PostgreSQL grouping or child orientation");
	}
	if (replayed_signatures.semantic != artifact_signatures.semantic) {
		ReplayError(artifact.path, "lowered DuckDB logical tree changed PostgreSQL preserved sides");
	}

	Printer::Print("[PGPLAN] {\"event\":\"imported\",\"artifact\":" + JSONQuote(artifact.path) +
	               ",\"query_sha256\":" + JSONQuote(artifact.query_sha256) +
	               ",\"query_sha256_verified\":true,\"query_sha256_unverified_reason\":null" +
	               ",\"plan_data\":" + JSONQuote(artifact.plan_data) +
	               ",\"plan_schema\":" + JSONQuote(artifact.plan_schema) +
	               ",\"artifact_raw_signature\":" + JSONQuote(artifact_signatures.raw) +
	               ",\"imported_raw_signature\":" + JSONQuote(replayed_signatures.raw) +
	               ",\"implied_equality_count\":" + to_string(implied_equality_count) +
	               ",\"expected_semantic_signature\":" + JSONQuote(artifact_signatures.semantic) + "}");

	PostgresPlanReplayResult result;
	result.plan = std::move(replayed_plan);
	result.artifact_path = artifact.path;
	result.query_sha256 = artifact.query_sha256;
	result.artifact_raw_signature = artifact_signatures.raw;
	result.expected_semantic_signature = artifact_signatures.semantic;
	result.occurrence_by_table_index = std::move(scan_inventory.occurrence_by_table_index);
	return result;
}

string PostgresPlanReplay::SemanticSignature(const LogicalOperator &plan) {
	auto inventory = BuildDuckScanInventory(plan, "<semantic-signature>");
	return LogicalPlanSignatures(plan, inventory.occurrence_by_table_index, "<semantic-signature>").semantic;
}

void PostgresPlanReplay::VerifyFinalPlan(const LogicalOperator &plan, const string &expected_semantic_signature,
	                                     const string &artifact_path) {
	auto inventory = BuildDuckScanInventory(plan, artifact_path);
	VerifyFinalPlan(plan, expected_semantic_signature, artifact_path, inventory.occurrence_by_table_index);
}

void PostgresPlanReplay::VerifyFinalPlan(const LogicalOperator &plan, const string &expected_semantic_signature,
	                                     const string &artifact_path,
	                                     const unordered_map<idx_t, idx_t> &occurrence_by_table_index) {
	auto final_signature = LogicalPlanSignatures(plan, occurrence_by_table_index, artifact_path).semantic;
	if (final_signature != expected_semantic_signature) {
		throw InvalidInputException(
		    "[PGPLAN] final semantic signature mismatch for artifact %s (expected=%s, final=%s)",
		    artifact_path.c_str(), expected_semantic_signature.c_str(), final_signature.c_str());
	}
	Printer::Print("[PGPLAN] {\"event\":\"verified\",\"artifact\":" + JSONQuote(artifact_path) +
	               ",\"expected_semantic_signature\":" + JSONQuote(expected_semantic_signature) +
	               ",\"final_semantic_signature\":" + JSONQuote(final_signature) + "}");
}

} // namespace duckdb
