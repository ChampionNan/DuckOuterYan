#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"

#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>

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

void OuterYanTrace::Decision(bool outer_reordered, bool cost_gate_applied, bool outer_yan_selected,
                             const string &reason, const OuterYanDecisionCosts &costs) {
	if (!Enabled()) {
		return;
	}
	std::ostringstream line;
	line << std::setprecision(17)
	     << "[OY_DECISION] outer_reordered=" << (outer_reordered ? 1 : 0)
	     << " cost_gate_applied=" << (cost_gate_applied ? 1 : 0)
	     << " outer_yan_selected=" << (outer_yan_selected ? 1 : 0)
	     << " reason=" << reason;
	auto metric = [&](const char *name, double value) {
		line << " " << name << "=";
		if (costs.available) {
			line << value;
		} else {
			line << "NA";
		}
	};
	auto ratio_metric = [&](const char *name, double value) {
		line << " " << name << "=";
		if (costs.available) {
			line << std::setprecision(6) << value << std::setprecision(17);
		} else {
			line << "NA";
		}
	};
	metric("baseline_cost", costs.baseline_cost);
	metric("candidate_join_cost", costs.candidate_join_cost);
	metric("semijoin_raw_cost", costs.semijoin_raw_cost);
	ratio_metric("semijoin_cost_ratio", costs.semijoin_cost_ratio);
	metric("weighted_semijoin_cost", costs.weighted_semijoin_cost);
	metric("candidate_total", costs.candidate_total);
	ratio_metric("cost_ratio_limit", costs.cost_ratio_limit);
	metric("baseline_threshold", costs.baseline_threshold);
	metric("round1_build", costs.round1_build);
	metric("round1_probe", costs.round1_probe);
	metric("round2_build", costs.round2_build);
	metric("round2_probe", costs.round2_probe);
	line << "\n";
	Append(line.str());
}

} // namespace duckdb
