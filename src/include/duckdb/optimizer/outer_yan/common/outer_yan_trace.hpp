//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/string.hpp"
#include "duckdb/common/types.hpp"

namespace duckdb {

enum class OuterYanSelectedPlan : uint8_t { DUCKDB_BASELINE, OUTERYAN_CANDIDATE };
enum class OuterYanCostWinner : uint8_t { DUCKDB_BASELINE, OUTERYAN_CANDIDATE, EQUAL, UNAVAILABLE };
enum class OuterYanGateResult : uint8_t { PASS, FAIL, SKIPPED, UNAVAILABLE };

//! Numeric inputs to the final OuterYan selection. Kept as a plain trace
//! carrier so the experiment harness can export the exact comparison without
//! depending on DP implementation types.
struct OuterYanDecisionCosts {
	bool available = false;
	string formula_id = "OUTER_YAN_COST_V6";
	//! The generic table-filter estimate was also checked with unfiltered base
	//! cardinalities. The selected flag means that conservative scenario was
	//! the limiting (higher candidate/baseline ratio) gate input.
	bool default_filter_upper_bound_checked = false;
	bool default_filter_upper_bound_selected = false;
	//! The selected candidate's join estimates needed the all-INNER
	//! full-reduction lower-bound correction. The strict gate may still use the
	//! corrected score, but the confidence-aware stretch tier may not.
	bool full_reduction_cardinality_lower_bound_applied = false;
	//! Risk guard for an unknown-selectivity filter on a tiny relation when the
	//! reducers retain almost all estimated input rows.
	bool uncertain_filter_amplification_guard = false;
	double semijoin_retained_cardinality_ratio = 0.0;
	double uncertain_filter_cardinality_amplification = 0.0;
	double baseline_cost = 0.0;
	double candidate_join_cost = 0.0;
	//! Sum of build/probe-side input rows across the real joins in each tree.
	double baseline_join_input_rows = 0.0;
	double candidate_join_input_rows = 0.0;
	double candidate_to_baseline_join_input_ratio = 0.0;
	bool candidate_to_baseline_join_input_ratio_available = false;
	//! True when planner-visible confidence signals permit the relaxed cost
	//! ceiling. This does not itself mean the candidate passed that ceiling.
	bool stretch_cost_gate_eligible = false;
	//! Raw sum of the four round build/probe estimates below.
	double semijoin_raw_cost = 0.0;
	//! Calibration applied once to semijoin_raw_cost by the final gate.
	double semijoin_cost_ratio = 0.0;
	//! semijoin_cost_ratio * semijoin_raw_cost.
	double weighted_semijoin_cost = 0.0;
	//! candidate_join_cost + weighted_semijoin_cost.
	double candidate_total = 0.0;
	double cost_ratio_limit = 0.0;
	double baseline_threshold = 0.0;
	double round1_build = 0.0;
	double round1_probe = 0.0;
	double round2_build = 0.0;
	double round2_probe = 0.0;
	//! Planned semi-join applications and newly constructed filters per round.
	//! A reused filter contributes a pair but not another filter build.
	idx_t round1_pairs = 0;
	idx_t round1_filters = 0;
	idx_t round2_pairs = 0;
	idx_t round2_filters = 0;
	//! Raw candidate-vs-baseline comparison (not the policy threshold).
	double raw_cost_delta = 0.0;
	double raw_cost_ratio = 0.0;
	bool raw_cost_ratio_available = false;
	//! Exact operands and margin of the policy comparison.
	double gate_lhs = 0.0;
	double gate_rhs = 0.0;
	double gate_margin = 0.0;
	//! Row-work coefficients used to produce the join/SJ totals.
	double inner_output_weight = 0.0;
	double unmatched_left_weight = 0.0;
	double unmatched_right_weight = 0.0;
	double semijoin_materialize_weight = 0.0;
	double semijoin_filter_build_weight = 0.0;
	double semijoin_replay_weight = 0.0;
	double semijoin_probe_lookup_weight = 0.0;
	double semijoin_probe_emit_weight = 0.0;
};

//! Authoritative final policy decision. The optimizer, trace, and experiment
//! harness all consume this record so selection cannot be inferred differently
//! in different layers.
struct OuterYanDecisionRecord {
	string selection_mode = "GATED";
	bool outer_reordered = false;
	bool cost_gate_applied = false;
	//! True only when a candidate that lost the strict 1.0 comparison was
	//! selected through the confidence-aware stretch tier.
	bool stretch_cost_gate_selected = false;
	bool outer_yan_selected = false;
	bool baseline_proven_empty = false;
	OuterYanSelectedPlan selected_plan = OuterYanSelectedPlan::DUCKDB_BASELINE;
	OuterYanCostWinner raw_cost_winner = OuterYanCostWinner::UNAVAILABLE;
	OuterYanGateResult gate_result = OuterYanGateResult::SKIPPED;
	string reason = "INAPPLICABLE";
	OuterYanDecisionCosts costs;
};

//! Opt-in, file-based pipeline tracer for the OuterYan optimizer.
//!
//! Every OuterYan pass appends a labelled snapshot of the representation it
//! just produced — the input logical plan, the OT/OJT after each rewrite, the
//! recorded semi-join pairs, and the rebuilt logical plan after SJ insertion /
//! aggregate pushdown — so a wrong-answer query can be replayed once and the
//! misfiring stage located by reading a single file. The stage order is
//! exactly the runtime pipeline order, since the calls sit inline in
//! `optimizer.cpp` and the three pass drivers.
//!
//! Activation: set the environment variable `DUCKDB_OYTRACE` to a writable
//! file path. Unset (the default) makes every entry point a cheap no-op, so
//! the calls can stay compiled into every build with no measurable cost.
//! Output is appended — one file can accumulate several queries; `BeginQuery`
//! writes a separator banner so blocks stay readable.
class OuterYanTrace {
public:
	//! True iff `DUCKDB_OYTRACE` names a non-empty path. Resolved once and
	//! cached for the process lifetime.
	static bool Enabled();

	//! Open a new query block: a separator banner followed by the original SQL
	//! (verbatim). Safe to pass an empty string when the text is unavailable.
	static void BeginQuery(const string &sql);

	//! Append one labelled stage. `body` is emitted verbatim under a header
	//! banner; a trailing newline is ensured.
	static void Stage(const string &label, const string &body);

	//! Append one machine-readable final candidate decision. The experiment
	//! harness consumes this record instead of inferring the decision from the
	//! presence of SJ operators (which cannot represent a changed-but-rejected
	//! candidate).
	static void Decision(const OuterYanDecisionRecord &record);

private:
	OuterYanTrace() = delete;
};

} // namespace duckdb
