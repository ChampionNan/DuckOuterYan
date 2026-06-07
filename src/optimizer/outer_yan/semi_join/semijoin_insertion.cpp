#include "duckdb/optimizer/outer_yan/semi_join/semijoin_insertion.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/function/table_function.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/planner/operator/logical_get.hpp"
#include "duckdb/storage/statistics/base_statistics.hpp"
#include "duckdb/storage/statistics/numeric_stats.hpp"

#include <algorithm>
#include <utility>

namespace duckdb {

// Map each filter's ColumnBindings to positional indices within
// `child_bindings`. Mirrors DPT's pre-resolved `bound_cols_*`. Both inputs
// are small (≤ a few filters per operator; ≤ a few keys per filter), so
// the linear scan is fine. A missing binding is an InternalException: the
// SJ operator's child must produce every binding referenced by the SJ key.
vector<vector<idx_t>>
SemijoinInsertion::ResolveColIds(const vector<ColumnBinding> &child_bindings,
                                 const vector<vector<ColumnBinding>> &per_filter_bindings) {
	vector<vector<idx_t>> result;
	result.reserve(per_filter_bindings.size());
	for (auto &filter_bindings : per_filter_bindings) {
		vector<idx_t> ids;
		ids.reserve(filter_bindings.size());
		for (auto &binding : filter_bindings) {
			bool found = false;
			for (idx_t i = 0; i < child_bindings.size(); i++) {
				if (child_bindings[i] == binding) {
					ids.push_back(i);
					found = true;
					break;
				}
			}
			if (!found) {
				throw InternalException(
				    "SemijoinInsertion::ResolveColIds: binding (%llu, %llu) not found "
				    "in child's column bindings",
				    static_cast<unsigned long long>(binding.table_index.index),
				    static_cast<unsigned long long>(binding.column_index.GetIndexUnsafe()));
			}
		}
		result.emplace_back(std::move(ids));
	}
	return result;
}

bool SemijoinInsertion::IsFilterGetBase(const LogicalOperator &node) {
	return node.type == LogicalOperatorType::LOGICAL_FILTER && node.children.size() == 1 && node.children[0] &&
	       node.children[0]->type == LogicalOperatorType::LOGICAL_GET;
}

void SemijoinInsertion::InsertAtBase(unique_ptr<LogicalOperator> &node, RelationId rid) {
	auto it = stacks_.find(rid);
	if (it == stacks_.end() || it->second.empty()) {
		return;
	}
	// LogicalSJBuild / LogicalSJProbe are schema pass-through, so every op in
	// the stack sees the base's column bindings — resolve all key bindings
	// against this one set rather than re-deriving them per level.
	const auto base_bindings = node->GetColumnBindings();

	unique_ptr<LogicalOperator> current = std::move(node);
	for (auto &entry : it->second) { // front (innermost) → back (outermost)
		auto resolved = ResolveColIds(base_bindings, entry.bindings_per_filter);
		if (entry.is_build) {
			entry.op->Cast<LogicalSJBuild>().build_col_ids_per_filter = std::move(resolved);
		} else {
			entry.op->Cast<LogicalSJProbe>().probe_col_ids_per_filter = std::move(resolved);
		}
		entry.op->children.emplace_back(std::move(current));
		current = std::move(entry.op);
	}
	it->second.clear(); // empty stack == "spliced"; the post-walk check relies on this
	node = std::move(current);
}

void SemijoinInsertion::InsertionTraverse(unique_ptr<LogicalOperator> &node) {
	if (!node) {
		return;
	}

	// Base unit A: LogicalFilter + LogicalGet treated as a unit, insert above filter.
	if (IsFilterGetBase(*node)) {
		auto &get = node->children[0]->Cast<LogicalGet>();
		auto it = table_to_relation_->find(get.table_index.index);
		if (it != table_to_relation_->end()) {
			InsertAtBase(node, it->second);
		}
		return;
	}

	// Base unit B: bare LogicalGet.
	if (node->type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = node->Cast<LogicalGet>();
		auto it = table_to_relation_->find(get.table_index.index);
		if (it != table_to_relation_->end()) {
			InsertAtBase(node, it->second);
		}
		return;
	}

	// Non-base node: recurse to find base units further down. This is how
	// SJ wraps land below pushed-down aggregates / projections sitting
	// between a join and a Get.
	for (auto &child : node->children) {
		InsertionTraverse(child);
	}
}

optional_ptr<LogicalGet> SemijoinInsertion::FindLogicalGet(LogicalOperator &node, idx_t table_idx) {
	if (node.type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = node.Cast<LogicalGet>();
		if (get.table_index.index == table_idx) {
			return &get;
		}
	}
	for (auto &child : node.children) {
		if (!child) {
			continue;
		}
		if (auto found = FindLogicalGet(*child, table_idx)) {
			return found;
		}
	}
	return nullptr;
}

bool SemijoinInsertion::LookupBaseStatsRange(LogicalOperator &root, ColumnBinding binding, ClientContext &context,
                                             int64_t &out_min, int64_t &out_max) {
	auto get_ptr = FindLogicalGet(root, binding.table_index.index);
	if (!get_ptr) {
		return false;
	}
	auto &get = *get_ptr;
	// ColumnBinding::column_index is the projection index within
	// get.GetColumnIds() — matches the binding StatisticsPropagator constructs
	// at src/optimizer/statistics/operator/propagate_get.cpp:189.
	auto col_idx_raw = binding.column_index.GetIndexUnsafe();
	auto &column_ids = get.GetColumnIds();
	if (col_idx_raw >= column_ids.size()) {
		return false;
	}
	unique_ptr<BaseStatistics> stats;
	if (get.function.statistics_extended) {
		TableFunctionGetStatisticsInput input(get.bind_data.get(), column_ids[col_idx_raw]);
		stats = get.function.statistics_extended(context, input);
	} else if (get.function.statistics) {
		stats = get.function.statistics(context, get.bind_data.get(), column_ids[col_idx_raw].GetPrimaryIndex());
	}
	if (!stats || !NumericStats::HasMinMax(*stats)) {
		return false;
	}
	Value min_v, max_v;
	try {
		min_v = NumericStats::Min(*stats).DefaultCastAs(LogicalType::BIGINT);
		max_v = NumericStats::Max(*stats).DefaultCastAs(LogicalType::BIGINT);
	} catch (...) {
		// UBIGINT / UHUGEINT / other types whose stats don't cleanly cast to
		// BIGINT are treated as "can't pre-decide" — fall through to runtime.
		return false;
	}
	if (min_v.IsNull() || max_v.IsNull()) {
		return false;
	}
	out_min = min_v.GetValue<int64_t>();
	out_max = max_v.GetValue<int64_t>();
	return true;
}

unique_ptr<LogicalOperator> SemijoinInsertion::Apply(unique_ptr<LogicalOperator> plan, const OuterYanTree &tree,
                                                     ClientContext &context, idx_t bitmap_byte_budget,
                                                     bool stats_prefilter_enabled) {
	if (!plan) {
		return plan;
	}

	const auto &bu = tree.bottom_up_pairs;
	const auto &td = tree.top_down_pairs;
	if (bu.empty() && td.empty()) {
		return plan;
	}

	// Re-use safety. OuterYanPost owns one SemijoinInsertion across plans;
	// clear any state left over from a prior Apply.
	stacks_.clear();
	table_to_relation_ = nullptr;

	// -------------------------------------------------------------------------
	// Build phase. Walk pairs in decision order (bottom_up then top_down),
	// growing each relation's nest stack and coalescing only adjacent
	// same-pass, same-kind ops.
	//
	//    The keyMapping key is function-local: the sorted set of build-side
	//    ColumnBindings (canonicalises {R.a, R.b} == {R.b, R.a}). Sharing
	//    spans probe relations — the filter is a read-only build-side data
	//    container after Finalize, and each probe relation gets its own
	//    LogicalSJProbe with its own ResolveColIds, so a shared filter does
	//    not couple their schemas. Each entry also stores the LogicalSJBuild
	//    that materialises the filter, so a reused filter's probe wires to it
	//    directly — no separate relation→build map.
	// -------------------------------------------------------------------------
	using ShareKey = vector<ColumnBinding>;
	struct ShareKeyHash {
		// FNV-1a 64-bit. Reference:
		//   - http://www.isthe.com/chongo/tech/comp/fnv/
		//   - https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
		// offset basis = 14695981039346656037   (0xcbf29ce484222325)
		// FNV prime    =      1099511628211     (0x00000100000001b3)
		size_t operator()(const ShareKey &k) const noexcept {
			constexpr uint64_t kFnvOffsetBasis = 14695981039346656037ULL;
			constexpr uint64_t kFnvPrime = 1099511628211ULL;
			uint64_t h = kFnvOffsetBasis;
			for (auto &b : k) {
				h ^= static_cast<uint64_t>(b.table_index.index);
				h *= kFnvPrime;
				// ProjectionIndex::index is private — go through the
				// public accessor that skips validity checks.
				h ^= static_cast<uint64_t>(b.column_index.GetIndexUnsafe());
				h *= kFnvPrime;
			}
			return static_cast<size_t>(h);
		}
	};

	// Sort a pair's keys by build binding. The shared filter hashes/compares
	// columns positionally (HashFilter folds them in list order), so build-col
	// position c must be the join partner of probe-col position c — both sides
	// must therefore share one column order. Sorting the (build, probe) keys
	// together also canonicalises {a,b} == {b,a} for filter sharing: pairs with
	// the same build-column set yield the same ShareKey, and each derives its
	// probe order from this same sort, so it matches the shared build order.
	auto sorted_keys = [](const OuterYanSemiPair &pair) -> vector<OuterYanSemiKey> {
		auto keys = pair.keys; // copy; sorted by build binding below
		std::sort(keys.begin(), keys.end(), [](const OuterYanSemiKey &a, const OuterYanSemiKey &b) {
			const auto &ba = a.build_binding;
			const auto &bb = b.build_binding;
			if (ba.table_index.index != bb.table_index.index) {
				return ba.table_index.index < bb.table_index.index;
			}
			// ProjectionIndex exposes operator< on its internal index.
			return ba.column_index < bb.column_index;
		});
		return keys;
	};

	unordered_map<ShareKey, std::pair<shared_ptr<SemiJoinFilter>, LogicalSJBuild *>, ShareKeyHash> keyMapping;

	// Append `filter` as a build on relation `rid`'s stack. Coalesces into the
	// current top op when it is a same-pass build; otherwise opens a new
	// LogicalSJBuild. Returns the (possibly pre-existing) build op so the
	// paired probe can reference it: the op lives on the heap behind the
	// stack's unique_ptr, so the pointer stays valid across later stack growth
	// and across the eventual splice into the plan.
	auto push_build = [&](RelationId rid, bool top_down, const shared_ptr<SemiJoinFilter> &filter,
	                      const vector<ColumnBinding> &build_keys) -> LogicalSJBuild * {
		auto &stk = stacks_[rid];
		if (!stk.empty() && stk.back().is_build && stk.back().top_down == top_down) {
			auto &build = stk.back().op->Cast<LogicalSJBuild>();
			build.sj_to_create.emplace_back(filter);
			stk.back().bindings_per_filter.emplace_back(build_keys);
			return &build;
		}
		auto build = make_uniq<LogicalSJBuild>(vector<shared_ptr<SemiJoinFilter>> {filter});
		auto *raw = build.get();
		vector<vector<ColumnBinding>> binds;
		binds.emplace_back(build_keys);
		stk.emplace_back(std::move(build), /*is_build=*/true, top_down, std::move(binds));
		return raw;
	};

	// Append `filter` as a probe of `build` on relation `rid`'s stack.
	// Coalesces into a same-pass probe top; otherwise opens a new
	// LogicalSJProbe. Each filter keeps its own related build, index-aligned
	// with sj_to_use.
	auto push_probe = [&](RelationId rid, bool top_down, const shared_ptr<SemiJoinFilter> &filter,
	                      vector<ColumnBinding> probe_keys, LogicalSJBuild *build) {
		auto &stk = stacks_[rid];
		if (!stk.empty() && !stk.back().is_build && stk.back().top_down == top_down) {
			auto &probe = stk.back().op->Cast<LogicalSJProbe>();
			probe.sj_to_use.emplace_back(filter);
			probe.AddDownStreamOperator(build);
			stk.back().bindings_per_filter.emplace_back(std::move(probe_keys));
			return;
		}
		auto probe = make_uniq<LogicalSJProbe>(vector<shared_ptr<SemiJoinFilter>> {filter});
		probe->AddDownStreamOperator(build);
		vector<vector<ColumnBinding>> binds;
		binds.emplace_back(std::move(probe_keys));
		stk.emplace_back(std::move(probe), /*is_build=*/false, top_down, std::move(binds));
	};

	auto process_pair = [&](const OuterYanSemiPair &pair, bool top_down) {
		// One sort drives both sides: `key` is the sorted build-binding set
		// (the ShareKey), and `probe_keys` are the probe bindings in that same
		// order, so build_col_ids[c] and probe_col_ids[c] are join partners —
		// for this pair and for any other pair that reuses the shared filter.
		const auto skeys = sorted_keys(pair);
		ShareKey key;
		vector<ColumnBinding> probe_keys;
		key.reserve(skeys.size());
		probe_keys.reserve(skeys.size());
		for (auto &k : skeys) {
			key.emplace_back(k.build_binding);
			probe_keys.emplace_back(k.probe_binding);
		}

		auto it = keyMapping.find(key);
		shared_ptr<SemiJoinFilter> filter;
		LogicalSJBuild *build = nullptr;
		if (it == keyMapping.end()) {
			filter = make_shared_ptr<SemiJoinFilter>();
			// Stats-prefilter (opt-in): only single-column keys are bitmap-
			// eligible. If base-table min/max predicts the implied bitmap
			// would exceed the byte budget, tag force_hash so
			// PhysicalSJBuild::Finalize skips the wasted TryBuild scan.
			if (stats_prefilter_enabled && key.size() == 1) {
				int64_t min_v = 0;
				int64_t max_v = 0;
				if (LookupBaseStatsRange(*plan, key[0], context, min_v, max_v)) {
					const auto range = static_cast<uint64_t>(max_v - min_v) + 1ULL;
					const auto bytes_needed = (range + 7ULL) / 8ULL;
					if (bytes_needed > bitmap_byte_budget) {
						filter->ForceHash();
					}
				}
			}
			// A fresh filter is built exactly once, on its build relation, in
			// the pass that first decided it.
			build = push_build(pair.build, top_down, filter, key);
			keyMapping.emplace(std::move(key), std::make_pair(filter, build));
		} else {
			filter = it->second.first;
			build = it->second.second;
		}

		push_probe(pair.probe, top_down, filter, std::move(probe_keys), build);
	};

	// Round order is a hard phase barrier, not a heuristic — the two-phase
	// Yannakakis full reducer (the O(IN + OUT) guarantee). A top_down reduction
	// may run only after EVERY bottom_up reduction has finished: the bottom-up
	// sweep culminates in the final semi-join reduce at the root, and only then
	// does the top-down sweep propagate the reduced result back to the leaves.
	// Consequence: a bottom_up build always finalises before any top_down op,
	// which is precisely why cross-round ops must never coalesce — the
	// `top_down == top_down` gate in push_build / push_probe. A bottom_up build
	// and a top_down build sit on opposite ends of that dependency chain and
	// cannot share one operator (merging them would close a Finalize cycle).
	for (auto &p : bu) {
		process_pair(p, /*top_down=*/false);
	}
	for (auto &p : td) {
		process_pair(p, /*top_down=*/true);
	}

	// -------------------------------------------------------------------------
	// Splice phase. Walk the rebuilt plan and splice each relation's nest
	// stack above its base unit (Filter+Get, or bare Get).
	// -------------------------------------------------------------------------
	table_to_relation_ = &tree.table_to_relation;
	InsertionTraverse(plan);

	// -------------------------------------------------------------------------
	// Every relation that accrued a nest stack must have been spliced at its
	// base (InsertAtBase empties the stack). A non-empty leftover means the
	// rebuilt plan is missing that relation's base unit — a structural error.
	// -------------------------------------------------------------------------
	for (auto &kv : stacks_) {
		if (!kv.second.empty()) {
			throw InternalException(
			    "SemijoinInsertion: semi-join ops for relation %llu were not inserted "
			    "(base unit for table_index not found in rebuilt plan)",
			    static_cast<unsigned long long>(kv.first));
		}
	}

	return plan;
}

} // namespace duckdb
