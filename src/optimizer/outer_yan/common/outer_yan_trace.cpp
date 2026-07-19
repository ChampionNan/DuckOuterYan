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

const char *SelectedPlanToString(OuterYanSelectedPlan plan) {
	switch (plan) {
	case OuterYanSelectedPlan::DUCKDB_BASELINE:
		return "DUCKDB";
	case OuterYanSelectedPlan::OUTERYAN_CANDIDATE:
		return "OUTERYAN";
	}
	return "UNKNOWN";
}

const char *CostWinnerToString(OuterYanCostWinner winner) {
	switch (winner) {
	case OuterYanCostWinner::DUCKDB_BASELINE:
		return "DUCKDB";
	case OuterYanCostWinner::OUTERYAN_CANDIDATE:
		return "OUTERYAN";
	case OuterYanCostWinner::EQUAL:
		return "EQUAL";
	case OuterYanCostWinner::UNAVAILABLE:
		return "UNAVAILABLE";
	}
	return "UNAVAILABLE";
}

const char *GateResultToString(OuterYanGateResult result) {
	switch (result) {
	case OuterYanGateResult::PASS:
		return "PASS";
	case OuterYanGateResult::FAIL:
		return "FAIL";
	case OuterYanGateResult::SKIPPED:
		return "SKIPPED";
	case OuterYanGateResult::UNAVAILABLE:
		return "UNAVAILABLE";
	}
	return "UNAVAILABLE";
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

void OuterYanTrace::Decision(const OuterYanDecisionRecord &record) {
	if (!Enabled()) {
		return;
	}
	const auto &costs = record.costs;
	std::ostringstream line;
	line << std::setprecision(17)
	     << "[OY_DECISION] formula_id=" << costs.formula_id
	     << " selection_mode=" << record.selection_mode
	     << " selected_plan=" << SelectedPlanToString(record.selected_plan)
	     << " outer_reordered=" << (record.outer_reordered ? 1 : 0)
	     << " cost_gate_applied=" << (record.cost_gate_applied ? 1 : 0)
	     << " outer_yan_selected=" << (record.outer_yan_selected ? 1 : 0)
	     << " baseline_proven_empty=" << (record.baseline_proven_empty ? 1 : 0)
	     << " reason=" << record.reason
	     << " raw_cost_winner=" << CostWinnerToString(record.raw_cost_winner)
	     << " gate_result=" << GateResultToString(record.gate_result);
	auto metric = [&](const char *name, double value, bool available) {
		line << " " << name << "=";
		if (available) {
			line << value;
		} else {
			line << "NA";
		}
	};
	auto ratio_metric = [&](const char *name, double value, bool available) {
		line << " " << name << "=";
		if (available) {
			line << std::setprecision(6) << value << std::setprecision(17);
		} else {
			line << "NA";
		}
	};
	auto count_metric = [&](const char *name, idx_t value, bool available) {
		line << " " << name << "=";
		if (available) {
			line << value;
		} else {
			line << "NA";
		}
	};
	metric("baseline_cost", costs.baseline_cost, costs.available);
	metric("candidate_join_cost", costs.candidate_join_cost, costs.available);
	metric("semijoin_raw_cost", costs.semijoin_raw_cost, costs.available);
	ratio_metric("semijoin_cost_ratio", costs.semijoin_cost_ratio, costs.available);
	metric("weighted_semijoin_cost", costs.weighted_semijoin_cost, costs.available);
	metric("candidate_total", costs.candidate_total, costs.available);
	ratio_metric("cost_ratio_limit", costs.cost_ratio_limit, costs.available);
	metric("baseline_threshold", costs.baseline_threshold, costs.available);
	metric("round1_build", costs.round1_build, costs.available);
	metric("round1_probe", costs.round1_probe, costs.available);
	metric("round2_build", costs.round2_build, costs.available);
	metric("round2_probe", costs.round2_probe, costs.available);
	count_metric("round1_pairs", costs.round1_pairs, costs.available);
	count_metric("round1_filters", costs.round1_filters, costs.available);
	count_metric("round2_pairs", costs.round2_pairs, costs.available);
	count_metric("round2_filters", costs.round2_filters, costs.available);
	metric("raw_cost_delta", costs.raw_cost_delta, costs.available);
	metric("raw_cost_ratio", costs.raw_cost_ratio, costs.available && costs.raw_cost_ratio_available);
	metric("gate_lhs", costs.gate_lhs, costs.available);
	metric("gate_rhs", costs.gate_rhs, costs.available);
	metric("gate_margin", costs.gate_margin, costs.available);
	ratio_metric("inner_output_weight", costs.inner_output_weight, costs.available);
	ratio_metric("unmatched_left_weight", costs.unmatched_left_weight, costs.available);
	ratio_metric("unmatched_right_weight", costs.unmatched_right_weight, costs.available);
	ratio_metric("semijoin_materialize_weight", costs.semijoin_materialize_weight, costs.available);
	ratio_metric("semijoin_filter_build_weight", costs.semijoin_filter_build_weight, costs.available);
	ratio_metric("semijoin_replay_weight", costs.semijoin_replay_weight, costs.available);
	ratio_metric("semijoin_probe_lookup_weight", costs.semijoin_probe_lookup_weight, costs.available);
	ratio_metric("semijoin_probe_emit_weight", costs.semijoin_probe_emit_weight, costs.available);
	line << "\n";
	Append(line.str());
}

} // namespace duckdb
