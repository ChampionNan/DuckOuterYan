//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/string.hpp"

namespace duckdb {

//! Numeric inputs to the final OuterYan selection. Kept as a plain trace
//! carrier so the experiment harness can export the exact comparison without
//! depending on DP implementation types.
struct OuterYanDecisionCosts {
	bool available = false;
	double baseline_cost = 0.0;
	double candidate_join_cost = 0.0;
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
	static void Decision(bool outer_reordered, bool cost_gate_applied, bool outer_yan_selected,
	                     const string &reason, const OuterYanDecisionCosts &costs = {});

private:
	OuterYanTrace() = delete;
};

} // namespace duckdb
