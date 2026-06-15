#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"

#include <cstdlib>
#include <fstream>
#include <mutex>

namespace duckdb {

namespace {

//! Environment variable that both enables tracing and names the sink file.
constexpr const char *kTraceEnvVar = "DUCKDB_OYTRACE";

//! Serialises appends from connections that plan concurrently so interleaved
//! queries never shred one another's blocks. Planning is off the hot path, so
//! one global mutex is adequate.
std::mutex &TraceMutex() {
	static std::mutex m;
	return m;
}

//! Env-var lookup, resolved once. An unset / empty variable disables tracing
//! for the whole process. Returns the path, or an empty string when disabled.
const string &TracePath() {
	static const string path = []() -> string {
		const char *p = std::getenv(kTraceEnvVar);
		return (p && p[0]) ? string(p) : string();
	}();
	return path;
}

void Append(const string &text) {
	const auto &path = TracePath();
	if (path.empty()) {
		return;
	}
	std::lock_guard<std::mutex> guard(TraceMutex());
	std::ofstream out(path, std::ios::app);
	if (out) {
		out << text;
	}
}

} // namespace

bool OuterYanTrace::Enabled() {
	return !TracePath().empty();
}

void OuterYanTrace::BeginQuery(const string &sql) {
	if (!Enabled()) {
		return;
	}
	string block = "\n";
	block += "################################################################################\n";
	block += "# OuterYan pipeline trace\n";
	if (!sql.empty()) {
		block += "# query: ";
		block += sql;
		if (sql.back() != '\n') {
			block += "\n";
		}
	}
	block += "################################################################################\n";
	Append(block);
}

void OuterYanTrace::Stage(const string &label, const string &body) {
	if (!Enabled()) {
		return;
	}
	string block = "\n==== ";
	block += label;
	block += " ====\n";
	block += body;
	if (body.empty() || body.back() != '\n') {
		block += "\n";
	}
	Append(block);
}

} // namespace duckdb
