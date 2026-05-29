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

unique_ptr<LogicalSJProbe>
SemijoinInsertion::MakeProbeOperator(RelationId rid, const vector<ColumnBinding> &child_bindings) {
	auto probe_it = probe_wraps_.find(rid);
	if (probe_it == probe_wraps_.end() || probe_it->second.empty()) {
		return nullptr;
	}
	auto &wraps = probe_it->second;

	// Three index-aligned vectors for the merged operator. Front-to-back
	// over `wraps` puts the earliest-decided filter at index 0, so
	// PhysicalSJProbe::ExecuteInternal applies it first.
	vector<shared_ptr<SemiJoinFilter>> filters;
	vector<vector<ColumnBinding>> per_filter_bindings;
	vector<LogicalSJBuild *> related_builds;
	filters.reserve(wraps.size());
	per_filter_bindings.reserve(wraps.size());
	related_builds.reserve(wraps.size());

	for (auto &pw : wraps) {
		filters.emplace_back(pw.filter);
		per_filter_bindings.emplace_back(pw.probe_bindings);
		auto rb_it = build_ptr_map_.find(pw.related_build_rid);
		if (rb_it == build_ptr_map_.end()) {
			throw InternalException(
			    "SemijoinInsertion: probe references unknown build relation %llu",
			    static_cast<unsigned long long>(pw.related_build_rid));
		}
		related_builds.emplace_back(rb_it->second);
	}

	auto probe = make_uniq<LogicalSJProbe>(std::move(filters));
	probe->probe_col_ids_per_filter = ResolveColIds(child_bindings, per_filter_bindings);
	for (auto *rb : related_builds) {
		probe->AddDownStreamOperator(rb);
	}
	return probe;
}

unique_ptr<LogicalSJBuild>
SemijoinInsertion::TakeBuildOperator(RelationId rid, const vector<ColumnBinding> &child_bindings) {
	auto it = pending_builds_.find(rid);
	if (it == pending_builds_.end() || !it->second) {
		return nullptr;
	}
	auto build = std::move(it->second);

	auto bb_it = build_bindings_by_rid_.find(rid);
	if (bb_it == build_bindings_by_rid_.end()) {
		throw InternalException(
		    "SemijoinInsertion: build for relation %llu has no recorded build bindings",
		    static_cast<unsigned long long>(rid));
	}
	build->build_col_ids_per_filter = ResolveColIds(child_bindings, bb_it->second);
	return build;
}

void SemijoinInsertion::InsertAtBase(unique_ptr<LogicalOperator> &node, RelationId rid) {
	// Whatever `node` currently is (bare LogicalGet or LogicalFilter+LogicalGet
	// unit) becomes the innermost. At most one merged probe wraps it; at most
	// one build wraps that. By construction the chain is never deeper than
	// `build → probe → base` at a single InsertAtBase call.
	unique_ptr<LogicalOperator> current = std::move(node);

	if (auto probe = MakeProbeOperator(rid, current->GetColumnBindings())) {
		probe->children.emplace_back(std::move(current));
		current = std::move(probe);
	}

	if (auto build = TakeBuildOperator(rid, current->GetColumnBindings())) {
		build->children.emplace_back(std::move(current));
		current = std::move(build);
	}

	node = std::move(current);
}

void SemijoinInsertion::InsertionTraverse(unique_ptr<LogicalOperator> &node) {
	if (!node) {
		return;
	}

	// Base unit A: LogicalFilter + LogicalGet treated atomically.
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
	probe_wraps_.clear();
	pending_builds_.clear();
	build_ptr_map_.clear();
	build_bindings_by_rid_.clear();
	table_to_relation_ = nullptr;

	// -------------------------------------------------------------------------
	// 1) Group pairs by shared-filter key → one shared SemiJoinFilter per
	//    group. Iteration order is bottom_up first, then top_down. Within a
	//    probe relation, earlier-iterated pairs end up earlier in
	//    probe_wraps_[rid] → first to apply inside PhysicalSJProbe.
	//
	//    The keyMapping key is function-local: the sorted set of build-side
	//    ColumnBindings (canonicalises {R.a, R.b} == {R.b, R.a}). Sharing
	//    spans probe relations — the filter is a read-only build-side data
	//    container after Finalize, and each probe relation gets its own
	//    LogicalSJProbe with its own ResolveColIds, so a shared filter does
	//    not couple their schemas. This collapses adjacent "build twice on
	//    the same column" duplicates inside LogicalSJBuild::sj_to_create.
	//    Lives only inside Apply, so we use the binding vector directly
	//    instead of introducing a new struct.
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

	auto construct_key = [](const OuterYanSemiPair &pair) -> ShareKey {
		vector<ColumnBinding> bindings;
		bindings.reserve(pair.keys.size());
		for (auto &k : pair.keys) {
			bindings.emplace_back(k.build_binding);
		}
		std::sort(bindings.begin(), bindings.end(),
		          [](const ColumnBinding &a, const ColumnBinding &b) {
			          if (a.table_index.index != b.table_index.index) {
				          return a.table_index.index < b.table_index.index;
			          }
			          // ProjectionIndex exposes operator< on its internal index.
			          return a.column_index < b.column_index;
		          });
		return bindings;
	};

	unordered_map<ShareKey, shared_ptr<SemiJoinFilter>, ShareKeyHash> keyMapping;
	// Filters per build relation, used to construct LogicalSJBuilds in
	// Phase 2. Local because it does not survive into Phase 3.
	unordered_map<RelationId, vector<shared_ptr<SemiJoinFilter>>> build_filters_by_rid;

	auto process_pair = [&](const OuterYanSemiPair &pair) {
		auto key = construct_key(pair);
		auto it = keyMapping.find(key);
		shared_ptr<SemiJoinFilter> filter;
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
			build_filters_by_rid[pair.build].emplace_back(filter);
			build_bindings_by_rid_[pair.build].emplace_back(key);
			keyMapping.emplace(std::move(key), filter);
		} else {
			filter = it->second;
		}

		ProbeWrap pw;
		pw.filter = filter;
		pw.related_build_rid = pair.build;
		pw.probe_bindings.reserve(pair.keys.size());
		for (auto &k : pair.keys) {
			pw.probe_bindings.emplace_back(k.probe_binding);
		}
		probe_wraps_[pair.probe].emplace_back(std::move(pw));
	};

	for (auto &p : bu) {
		process_pair(p);
	}
	for (auto &p : td) {
		process_pair(p);
	}

	// -------------------------------------------------------------------------
	// 2) Pre-create one LogicalSJBuild per build relation, holding ALL
	//    filters for that relation. Keep raw pointers in build_ptr_map_ so
	//    cross-relation probes can wire to the build's Finalize before the
	//    build itself has been inserted into the plan.
	// -------------------------------------------------------------------------
	for (auto &entry : build_filters_by_rid) {
		auto rid = entry.first;
		auto build = make_uniq<LogicalSJBuild>(std::move(entry.second));
		build_ptr_map_[rid] = build.get();
		pending_builds_.emplace(rid, std::move(build));
	}

	// -------------------------------------------------------------------------
	// 3) Walk the rebuilt plan and insert wraps at the filter+get unit (or
	//    bare get) for every relation that has wraps assigned.
	// -------------------------------------------------------------------------
	table_to_relation_ = &tree.table_to_relation;
	InsertionTraverse(plan);

	// -------------------------------------------------------------------------
	// 4) Every pre-created build must have been inserted into the plan. If a
	//    pending build is still around, the rebuilt plan is missing the
	//    LogicalGet for that relation — a structural inconsistency.
	// -------------------------------------------------------------------------
	for (auto &kv : pending_builds_) {
		if (kv.second) {
			throw InternalException(
			    "SemijoinInsertion: build for relation %llu was not inserted "
			    "(LogicalGet for table_index not found in rebuilt plan)",
			    static_cast<unsigned long long>(kv.first));
		}
	}

	return plan;
}

} // namespace duckdb
