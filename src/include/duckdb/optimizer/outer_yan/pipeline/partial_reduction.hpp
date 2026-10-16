#pragma once

#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"

namespace duckdb {

//! Order-aware reduction for projection/join plans. The selected OJT is not
//! rerooted: a separate undirected view owns only the reduction schedule.
class PartialReduction {
public:
	//! Replace the reference schedule only when a guarded partial schedule has
	//! strictly fewer pairs. Aggregate pushdown remains on the reference path.
	bool Apply(OuterYanTree &tree) const;
};

} // namespace duckdb
