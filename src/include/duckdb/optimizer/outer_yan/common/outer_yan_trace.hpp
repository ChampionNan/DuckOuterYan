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

private:
	OuterYanTrace() = delete;
};

} // namespace duckdb
