// Linux-only observer of the real OuterYan applicability gate.
// Build from the exact checkout used for libduckdb (class layout must match):
//   c++ -std=c++17 -O2 -fPIC -shared -isystem src/include \
//     auto_test/pg_plan_comparison/trace_applicability.cpp -ldl \
//     -o /absolute/path/trace_applicability.so
// Run diagnostic EXPLAIN only, with a client dynamically linked to libduckdb:
//   LD_PRELOAD=/absolute/path/trace_applicability.so /path/to/inspect_replay ...
// The repository CLI links duckdb_static, so preload cannot intercept its
// internally bound calls. The existing inspect_replay.cpp client uses libduckdb.
// Require one [OY_APPLICABILITY] record per target EXPLAIN. An absent record is
// an instrumentation failure (e.g. static linking), not an applicability result.
// Never preload this observer for reported performance measurements.
// Optional OY_APPLICABILITY_PLAN=1 emits the exact gate-input logical plan as a
// second JSON line. Use it only for selected diagnostic queries.

#if !defined(__linux__)
#error "trace_applicability.cpp requires Linux ELF interposition and RTLD_NEXT"
#endif

#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <exception>

namespace {

using CheckFunction = bool (*)(duckdb::OuterYanTree *, duckdb::LogicalOperator &, bool, bool);

CheckFunction OriginalCheck() {
	// This method's Itanium ABI symbol has no std::string/template components.
	// Defining the actual class method below gives our wrapper the same mangling.
	static const auto original = []() {
		constexpr auto symbol = "_ZN6duckdb12OuterYanTree18CheckApplicabilityERNS_15LogicalOperatorEbb";
		dlerror();
		auto address = dlsym(RTLD_NEXT, symbol);
		const auto error = dlerror();
		if (error || !address) {
			std::fprintf(stderr, "[OY_APPLICABILITY_ERROR] cannot resolve original %s: %s\n", symbol,
			             error ? error : "null function address");
			std::fflush(stderr);
			std::_Exit(78);
		}
		CheckFunction function;
		static_assert(sizeof(function) == sizeof(address), "unsupported function-pointer ABI");
		std::memcpy(&function, &address, sizeof(function));
		return function;
	}();
	return original;
}

const char *OperatorName(duckdb::LogicalOperatorType type) {
	// Avoid calling further DuckDB routines or allocating while observing it.
	using Type = duckdb::LogicalOperatorType;
#define OY_OPERATOR_NAME(name) case Type::name: return #name
	switch (type) {
		OY_OPERATOR_NAME(LOGICAL_PROJECTION);
		OY_OPERATOR_NAME(LOGICAL_FILTER);
		OY_OPERATOR_NAME(LOGICAL_AGGREGATE_AND_GROUP_BY);
		OY_OPERATOR_NAME(LOGICAL_WINDOW);
		OY_OPERATOR_NAME(LOGICAL_UNNEST);
		OY_OPERATOR_NAME(LOGICAL_LIMIT);
		OY_OPERATOR_NAME(LOGICAL_ORDER_BY);
		OY_OPERATOR_NAME(LOGICAL_TOP_N);
		OY_OPERATOR_NAME(LOGICAL_DISTINCT);
		OY_OPERATOR_NAME(LOGICAL_GET);
		OY_OPERATOR_NAME(LOGICAL_DELIM_GET);
		OY_OPERATOR_NAME(LOGICAL_EXPRESSION_GET);
		OY_OPERATOR_NAME(LOGICAL_DUMMY_SCAN);
		OY_OPERATOR_NAME(LOGICAL_EMPTY_RESULT);
		OY_OPERATOR_NAME(LOGICAL_CTE_REF);
		OY_OPERATOR_NAME(LOGICAL_COMPARISON_JOIN);
		OY_OPERATOR_NAME(LOGICAL_DELIM_JOIN);
		OY_OPERATOR_NAME(LOGICAL_ANY_JOIN);
		OY_OPERATOR_NAME(LOGICAL_CROSS_PRODUCT);
		OY_OPERATOR_NAME(LOGICAL_POSITIONAL_JOIN);
		OY_OPERATOR_NAME(LOGICAL_ASOF_JOIN);
		OY_OPERATOR_NAME(LOGICAL_DEPENDENT_JOIN);
		OY_OPERATOR_NAME(LOGICAL_SJ_BUILD);
		OY_OPERATOR_NAME(LOGICAL_SJ_PROBE);
		OY_OPERATOR_NAME(LOGICAL_UNION);
		OY_OPERATOR_NAME(LOGICAL_EXCEPT);
		OY_OPERATOR_NAME(LOGICAL_INTERSECT);
		OY_OPERATOR_NAME(LOGICAL_RECURSIVE_CTE);
		OY_OPERATOR_NAME(LOGICAL_MATERIALIZED_CTE);
		OY_OPERATOR_NAME(LOGICAL_EXPLAIN);
	default:
		return "OTHER_LOGICAL_OPERATOR";
	}
#undef OY_OPERATOR_NAME
}

void JSONString(const char *value) {
	std::fputc('"', stderr);
	for (const auto *cursor = reinterpret_cast<const unsigned char *>(value); *cursor; cursor++) {
		switch (*cursor) {
		case '"':
			std::fputs("\\\"", stderr);
			break;
		case '\\':
			std::fputs("\\\\", stderr);
			break;
		default:
			if (*cursor < 0x20) {
				std::fprintf(stderr, "\\u%04x", static_cast<unsigned>(*cursor));
			} else {
				std::fputc(*cursor, stderr);
			}
		}
	}
	std::fputc('"', stderr);
}

void LogResult(const duckdb::LogicalOperator &plan, const duckdb::ApplicabilityResult &result,
               bool applicable, bool require_outer, bool require_stable_intermediate_filters) {
	flockfile(stderr);
	std::fprintf(stderr, "[OY_APPLICABILITY] {\"applicable\":%s,\"stored_applicable\":%s,"
	                     "\"require_outer\":%s,\"require_stable_intermediate_filters\":%s,"
	                     "\"has_root_aggregate\":%s,\"root_operator_id\":%u,\"root_operator\":",
	             applicable ? "true" : "false", result.applicable ? "true" : "false",
	             require_outer ? "true" : "false", require_stable_intermediate_filters ? "true" : "false",
	             result.has_root_aggregate ? "true" : "false", static_cast<unsigned>(plan.type));
	JSONString(OperatorName(plan.type));
	std::fputs(",\"reason\":", stderr);
	JSONString(result.reason.c_str());
	// This bounded, read-only prefix distinguishes LIMIT/ORDER/CTE caps from
	// the first branching operator when the gate reports "not a SELECT join".
	std::fputs(",\"unary_prefix\":[", stderr);
	const auto *node = &plan;
	for (unsigned depth = 0; depth < 16; depth++) {
		if (depth) {
			std::fputc(',', stderr);
		}
		JSONString(OperatorName(node->type));
		if (node->children.size() != 1 || !node->children[0]) {
			break;
		}
		node = node->children[0].get();
	}
	std::fputs("]}\n", stderr);
	std::fflush(stderr);
	funlockfile(stderr);
}

void LogPlanIfRequested(const duckdb::LogicalOperator &plan) {
	const auto enabled = std::getenv("OY_APPLICABILITY_PLAN");
	if (!enabled || !enabled[0] || std::strcmp(enabled, "0") == 0) {
		return;
	}
	try {
		// Rendering is observational. Do it before locking stderr so a rendering
		// failure cannot leave the stream locked or change the original gate result.
		const auto rendered = plan.ToString(duckdb::ExplainFormat::JSON);
		flockfile(stderr);
		std::fputs("[OY_APPLICABILITY_PLAN] {\"format\":\"duckdb_logical_explain_json\",\"plan\":", stderr);
		JSONString(rendered.c_str());
		std::fputs("}\n", stderr);
		std::fflush(stderr);
		funlockfile(stderr);
	} catch (const std::exception &error) {
		flockfile(stderr);
		std::fputs("[OY_APPLICABILITY_PLAN_ERROR] {\"error\":", stderr);
		JSONString(error.what());
		std::fputs("}\n", stderr);
		std::fflush(stderr);
		funlockfile(stderr);
	} catch (...) {
		std::fputs("[OY_APPLICABILITY_PLAN_ERROR] {\"error\":\"unknown rendering error\"}\n", stderr);
		std::fflush(stderr);
	}
}

} // namespace

namespace duckdb {

__attribute__((visibility("default"))) bool
OuterYanTree::CheckApplicability(LogicalOperator &plan, bool require_outer,
                                bool require_stable_intermediate_filters) {
	const auto entry_errno = errno;
	const auto original = OriginalCheck();
	errno = entry_errno;
	const auto applicable = original(this, plan, require_outer, require_stable_intermediate_filters);
	const auto original_errno = errno;
	LogResult(plan, Applicability(), applicable, require_outer, require_stable_intermediate_filters);
	LogPlanIfRequested(plan);
	errno = original_errno;
	return applicable;
}

} // namespace duckdb
