#include "duckdb/optimizer/outer_yan/pipeline/outer_yan_dp.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/limits.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/join_order/relation_statistics_helper.hpp"
#include "duckdb/optimizer/outer_yan/common/operator_tree.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_trace.hpp"
#include "duckdb/optimizer/outer_yan/common/outer_yan_tree.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"
#include "duckdb/planner/expression_iterator.hpp"
#include "duckdb/planner/operator/logical_comparison_join.hpp"
#include "duckdb/planner/operator/logical_filter.hpp"
#include "duckdb/planner/operator/logical_get.hpp"
#include "duckdb/planner/operator/logical_projection.hpp"

#include <algorithm>
#include <cmath>
#include <set>

namespace duckdb {

// ============================================================================
// OuterYanDP -- construction
// ============================================================================

OuterYanDP::OuterYanDP(ClientContext &context_p, OuterYanDPCostParameters cost_parameters_p)
	    : context(context_p), cost_parameters(cost_parameters_p) {
}

OuterYanDPCostSummary OuterYanDP::Optimize(OuterYanTree &tree) {
	if (!tree.HasOT()) {
		throw InternalException("OuterYanDP::Optimize: tree.ot is null");
	}

	OuterYanDPCostSummary summary;
	summary.parameters = cost_parameters;
	BuildLeafRelations(tree);
	BuildEdgesFromOT(tree);
	BuildSemijoinCostModel(tree, summary);
	PopulateOutputRelations(tree);

	if (num_relations <= 1) {
		// Nothing to enumerate. Still surface an OJT for the lone relation so
		// OuterYanPost has a valid tree to lower (an accepted query always has
		// >= 2 relations, so the 0-relation case is unreachable here).
		if (num_relations == 1) {
			tree.BuildOJT();
			summary.has_complete_plan = true;
		}
		return summary;
	}

	unordered_set<RelationIndex> bindings;
	for (idx_t i = 0; i < num_relations; i++) {
		bindings.emplace(RelationIndex(i));
	}
	auto &full_set = set_manager.GetJoinRelation(bindings);

	// First attempt: `FIX_ALL_OUTPUTS` when the query anchors outputs,
	// otherwise unconstrained (`NONE`). Subsequent attempts pin each output
	// relation as the sole `FIX_ONE_OUTPUT` candidate in turn -- only useful
	// when an anchor exists, so they are skipped under `NONE`. The cheapest
	// plan over all attempts wins. Re-running the winning attempt
	// deterministically (rather than snapshotting the chosen plan) keeps the
	// memo management trivial; small `num_relations` makes the 2x cost
	// acceptable.
	const auto primary_mode = output_relations.empty() ? RootFixMode::NONE
	                                                    : RootFixMode::FIX_ALL_OUTPUTS;
	vector<RelationIndex> fix_one_candidates(output_relations.begin(), output_relations.end());
	const idx_t total_attempts =
	    primary_mode == RootFixMode::NONE ? 1 : 1 + fix_one_candidates.size();

	double best_cost = NumericLimits<double>::Maximum();
	int64_t best_attempt = -1;
	for (idx_t attempt = 0; attempt < total_attempts; attempt++) {
		ResetForRetry(tree);
		if (attempt == 0) {
			fix_mode = primary_mode;
		} else {
			fix_mode = RootFixMode::FIX_ONE_OUTPUT;
			fixed_output_relation = fix_one_candidates[attempt - 1];
		}
		if (!RunEnumeration(tree)) {
			continue;
		}
		auto entry = plans.find(full_set);
		if (entry == plans.end()) {
			continue;
		}
		const double cost = entry->second->cost;
		if (cost < best_cost) {
			best_cost = cost;
			best_attempt = static_cast<int64_t>(attempt);
		}
	}

	// Fallback ladder. The root-fix regimes (FIX_ALL_OUTPUTS / FIX_ONE_OUTPUT)
	// can fail to connect every relation when an anchored output relation is a
	// cut vertex of the join graph -- e.g. the sole GROUP BY key is the centre
	// of a star, so every 2-set holding it is rejected while the only
	// anchor-free pair is disconnected. Root anchoring is a SOFT cost
	// preference (the group-by relation as tree root is desirable, not
	// required); correctness is established by the OJT lowering regardless of
	// order. So instead of abandoning the query we retry once UNCONSTRAINED
	// (`NONE`), which always connects an acyclic predicate graph. `use_none`
	// flags that the chosen plan is this retry.
	bool use_none = false;
	if (best_attempt < 0 && primary_mode != RootFixMode::NONE) {
		ResetForRetry(tree);
		fix_mode = RootFixMode::NONE;
		if (RunEnumeration(tree) && plans.find(full_set) != plans.end()) {
			use_none = true;
		}
	}

	if (best_attempt < 0 && !use_none) {
		// Even unconstrained enumeration could not connect all relations -- only
		// possible for a disconnected predicate graph, which the applicability
		// gate already rejects. Fall back to the post-Desimplify OT order so
		// OuterYanPost always receives a valid OJT instead of crashing with
		// "tree has no OJT".
		tree.BuildOJT();
		return summary;
	}

	// Re-run the winning attempt so `plans` is populated for RebuildOT.
	ResetForRetry(tree);
	if (use_none) {
		fix_mode = RootFixMode::NONE;
	} else if (best_attempt == 0) {
		fix_mode = primary_mode;
	} else {
		fix_mode = RootFixMode::FIX_ONE_OUTPUT;
		fixed_output_relation = fix_one_candidates[static_cast<idx_t>(best_attempt) - 1];
	}
	if (!RunEnumeration(tree) || plans.find(full_set) == plans.end()) {
		// Deterministic re-run cannot diverge from the winning attempt; fall
		// back to the OT order rather than leave the tree without an OJT.
		tree.BuildOJT();
		return summary;
	}

	summary.chosen_real_join_cost = plans.find(full_set)->second->cost;
	summary.has_complete_plan = true;
	RebuildOT(tree, full_set);
	summary.candidate_join_breakdown = ScoreCurrentJoinTreeDetailed(tree, &summary.reduced_cardinalities);
	if (!ApproxEqual(summary.candidate_join_breakdown.total_cost, summary.chosen_real_join_cost)) {
		throw InternalException("OuterYanDP: detailed candidate cost %.17g differs from DP cost %.17g",
		                        summary.candidate_join_breakdown.total_cost, summary.chosen_real_join_cost);
	}
	tree.BuildOJT();
	if (OuterYanTrace::Enabled()) {
		OuterYanTrace::Stage("after DP — cost-chosen join order (result OJT)", tree.OJT().PrintAsTree(true));
	}
	return summary;
}

// ============================================================================
// Root-fix constraint plumbing (FIX_ALL_OUTPUTS / FIX_ONE_OUTPUT)
// ============================================================================

void OuterYanDP::PopulateOutputRelations(OuterYanTree &tree) {
	output_relations.clear();
	for (auto rel_id : tree.root_relations) {
		if (rel_id < num_relations) {
			output_relations.emplace(RelationIndex(rel_id));
		}
	}
	num_non_output = num_relations - output_relations.size();
	fix_mode = output_relations.empty() ? RootFixMode::NONE : RootFixMode::FIX_ALL_OUTPUTS;
}

void OuterYanDP::ResetForRetry(OuterYanTree &tree) {
	plans.clear();
	pairs = 0;
	bailed_out = false;
	InitLeafPlans(tree);
}

bool OuterYanDP::RunEnumeration(OuterYanTree &tree) {
	if (num_relations >= THRESHOLD_TO_SWAP_TO_APPROXIMATE) {
		return SolveApproximately();
	}
	if (SolveExactly()) {
		return true;
	}
	// Pair cap tripped -- fall back to greedy (matches the original
	// Optimize-time fallback policy).
	plans.clear();
	pairs = 0;
	InitLeafPlans(tree);
	return SolveApproximately();
}

bool OuterYanDP::ViolatesRootFix(JoinRelationSet &set) const {
	if (set.count == num_relations) {
		// The final emit is unconditionally legal: output relations are
		// allowed to enter exactly here.
		return false;
	}
	switch (fix_mode) {
	case RootFixMode::NONE:
		return false;
	case RootFixMode::FIX_ALL_OUTPUTS: {
		idx_t outputs_in = 0;
		for (idx_t i = 0; i < set.count; i++) {
			if (output_relations.count(set.relations[i]) != 0) {
				outputs_in++;
			}
		}
		if (outputs_in == 0) {
			return false;  // Pure non-output subset -- always legal.
		}
		// Contains >=1 output relation: must already cover every non-output
		// relation, otherwise some non-output would be forced to enter above
		// an output relation in the final tree.
		const idx_t non_output_in = set.count - outputs_in;
		return non_output_in != num_non_output;
	}
	case RootFixMode::FIX_ONE_OUTPUT:
		for (idx_t i = 0; i < set.count; i++) {
			if (set.relations[i] == fixed_output_relation) {
				return true;
			}
		}
		return false;
	}
	return false;
}

// ============================================================================
// Setup
// ============================================================================

void OuterYanDP::BuildLeafRelations(OuterYanTree &tree) {
	auto &ot_relations = tree.ot_relations_by_id;
	num_relations = ot_relations.size();
	for (idx_t r = 0; r < num_relations; r++) {
		auto *rel = ot_relations[r];
		if (!rel || rel->kind != OTNode::Kind::RELATION) {
			throw InternalException("OuterYanDP: missing RELATION OTNode for id %llu", r);
		}
		auto *base = FindBaseGet(rel->origin);
		if (base && base->type == LogicalOperatorType::LOGICAL_GET) {
			auto &get = base->Cast<LogicalGet>();
			rel->stats = RelationStatisticsHelper::ExtractGetStats(get, context);
		}
		if (!rel->stats.stats_initialized) {
			rel->stats.cardinality = 1;
		}
	}
}

void OuterYanDP::BuildEdgeStatistics(OuterYanTree &tree) {
	auto &ot_joins = tree.ot_joins_by_order;
	auto &ot_relations = tree.ot_relations_by_id;

	for (auto *jn : ot_joins) {
		if (!jn || jn->kind != OTNode::Kind::JOIN || !jn->info) {
			throw InternalException("OuterYanDP: malformed JOIN OTNode in ot_joins_by_order");
		}
		auto &join_info = *jn->info;
		if (join_info.conditions.empty()) {
			throw InternalException("OuterYanDP: JOIN OTNode has no conditions");
		}

		// Each condition is its own equivalence class -- no transitivity.
		double d_left = 1.0;
		double d_right = 1.0;
		auto lhs_col_first = FirstColumnRef(join_info.conditions[0].GetLHS());
		auto rhs_col_first = FirstColumnRef(join_info.conditions[0].GetRHS());
		if (!lhs_col_first || !rhs_col_first) {
			throw InternalException("OuterYanDP: conditions[0] has no resolvable column refs");
		}
		for (auto &cond : join_info.conditions) {
			auto l_col = FirstColumnRef(cond.GetLHS());
			auto r_col = FirstColumnRef(cond.GetRHS());
			if (!l_col || !r_col) {
				continue;
			}
			idx_t l_d = LookupDistinctCount(ot_relations[join_info.cond_left_relation_id]->stats,
			                                l_col->binding.column_index);
			idx_t r_d = LookupDistinctCount(ot_relations[join_info.cond_right_relation_id]->stats,
			                                r_col->binding.column_index);
			d_left *= static_cast<double>(MaxValue<idx_t>(l_d, 1));
			d_right *= static_cast<double>(MaxValue<idx_t>(r_d, 1));
		}
		const auto &left_stats = ot_relations[join_info.cond_left_relation_id]->stats;
		const auto &right_stats = ot_relations[join_info.cond_right_relation_id]->stats;
		const bool left_empty = left_stats.stats_initialized && left_stats.cardinality == 0;
		const bool right_empty = right_stats.stats_initialized && right_stats.cardinality == 0;
		join_info.left_distinct_count = left_empty ? 0.0 : MaxValue<double>(d_left, 1.0);
		join_info.right_distinct_count = right_empty ? 0.0 : MaxValue<double>(d_right, 1.0);
		if (left_empty && right_empty) {
			join_info.distinct_count = 0.0;
		} else {
			join_info.distinct_count =
			    MaxValue<double>(MaxValue<double>(join_info.left_distinct_count,
			                                      join_info.right_distinct_count),
			                     1.0);
		}
	}
}

void OuterYanDP::BuildEdgesFromOT(OuterYanTree &tree) {
	BuildEdgeStatistics(tree);

	auto &ot_joins = tree.ot_joins_by_order;
	ot_joins_by_filter_index.clear();

	for (auto *jn : ot_joins) {
		if (!jn || jn->kind != OTNode::Kind::JOIN || !jn->info) {
			throw InternalException("OuterYanDP: malformed JOIN OTNode in ot_joins_by_order");
		}
		auto &join_info = *jn->info;
		auto lhs_col_first = FirstColumnRef(join_info.conditions[0].GetLHS());
		auto rhs_col_first = FirstColumnRef(join_info.conditions[0].GetRHS());
		if (!lhs_col_first || !rhs_col_first) {
			throw InternalException("OuterYanDP: conditions[0] has no resolvable column refs");
		}
		ColumnBinding lhs_binding = lhs_col_first->binding;
		ColumnBinding rhs_binding = rhs_col_first->binding;

		auto &left_set = set_manager.GetJoinRelation(RelationIndex(join_info.cond_left_relation_id));
		auto &right_set = set_manager.GetJoinRelation(RelationIndex(join_info.cond_right_relation_id));
		auto &combined_set = set_manager.Union(left_set, right_set);

		// One FilterInfo carrier per OT JOIN. `filter` stays null -- our cost
		// code never dereferences it; QueryGraphEdges uses only left_set /
		// right_set / set for indexing.
		auto fi = make_uniq<FilterInfo>(unique_ptr<Expression>(), combined_set, filter_infos.size(),
		                                static_cast<JoinType>(join_info.join_kind));
		fi->SetLeftSet(&left_set);
		fi->SetRightSet(&right_set);
		fi->left_binding = lhs_binding;
		fi->right_binding = rhs_binding;

		// Lock-step indexing: ot_joins_by_filter_index[fi->filter_index] == jn.
		ot_joins_by_filter_index.push_back(jn);
		auto *fi_ptr = fi.get();
		filter_infos.push_back(std::move(fi));

		query_graph.CreateEdge(left_set, right_set, fi_ptr);
		query_graph.CreateEdge(right_set, left_set, fi_ptr);
	}
}

void OuterYanDP::BuildSemijoinCostModel(OuterYanTree &tree, OuterYanDPCostSummary &summary) {
	semijoin_cardinality.resize(num_relations);
	vector<double> base_cardinality(num_relations);
	for (idx_t r = 0; r < num_relations; r++) {
		auto &stats = tree.ot_relations_by_id[r]->stats;
		base_cardinality[r] = static_cast<double>(stats.stats_initialized ? stats.cardinality
		                                                               : MaxValue<idx_t>(stats.cardinality, 1));
		semijoin_cardinality[r] = base_cardinality[r];
	}

	std::set<vector<std::pair<idx_t, idx_t>>> built_filters;
	idx_t round1_step = 0;
	idx_t round2_step = 0;
	auto process_pair = [&](const OuterYanSemiPair &pair, bool top_down) {
		if (pair.build >= num_relations || pair.probe >= num_relations) {
			throw InternalException("OuterYanDP::BuildSemijoinCostModel: relation id out of range");
		}
		const OTJoin *edge = nullptr;
		for (auto *jn : tree.ot_joins_by_order) {
			if (!jn || !jn->info) {
				continue;
			}
			auto &info = *jn->info;
			if ((info.cond_left_relation_id == pair.build && info.cond_right_relation_id == pair.probe) ||
			    (info.cond_left_relation_id == pair.probe && info.cond_right_relation_id == pair.build)) {
				edge = &info;
				break;
			}
		}
		if (!edge) {
			throw InternalException("OuterYanDP::BuildSemijoinCostModel: pair has no join edge");
		}

		const bool build_is_left = edge->cond_left_relation_id == pair.build;
		const double base_build_distinct = build_is_left ? edge->left_distinct_count : edge->right_distinct_count;
		const double base_probe_distinct = build_is_left ? edge->right_distinct_count : edge->left_distinct_count;
		const double build_cardinality = semijoin_cardinality[pair.build];
		const double before_probe = semijoin_cardinality[pair.probe];
		double build_scale = 0.0;
		if (base_cardinality[pair.build] > 0.0) {
			build_scale = MinValue<double>(1.0, build_cardinality / base_cardinality[pair.build]);
		}
		double probe_scale = 0.0;
		if (base_cardinality[pair.probe] > 0.0) {
			probe_scale = MinValue<double>(1.0, before_probe / base_cardinality[pair.probe]);
		}
		const double build_distinct =
		    build_cardinality == 0.0 ? 0.0 : MaxValue<double>(1.0, base_build_distinct * build_scale);
		const double probe_distinct =
		    before_probe == 0.0 ? 0.0 : MaxValue<double>(1.0, base_probe_distinct * probe_scale);
		double survival;
		if (before_probe == 0.0 || build_distinct == 0.0) {
			survival = 0.0;
		} else if (probe_distinct == 0.0) {
			// Defensive fallback for inconsistent statistics: do not invent a
			// reduction when the non-empty probe has no distinct estimate.
			survival = 1.0;
		} else {
			survival = MinValue<double>(1.0, build_distinct / probe_distinct);
		}
		const double after_probe = ClampPlanCardinality(before_probe * survival);

		vector<std::pair<idx_t, idx_t>> filter_key;
		filter_key.reserve(pair.keys.size());
		for (auto &key : pair.keys) {
			filter_key.emplace_back(key.build_binding.table_index.index,
			                        key.build_binding.column_index.GetIndexUnsafe());
		}
		std::sort(filter_key.begin(), filter_key.end());
		const bool filter_reused = !built_filters.insert(filter_key).second;
		OuterYanSemijoinCostStep detail;
		detail.round = top_down ? 2 : 1;
		detail.step = top_down ? ++round2_step : ++round1_step;
		detail.build_relation = pair.build;
		detail.probe_relation = pair.probe;
		detail.build_table_index = StableTableIndex(tree, pair.build);
		detail.probe_table_index = StableTableIndex(tree, pair.probe);
		detail.filter_reused = filter_reused;
		detail.build_cardinality = build_cardinality;
		detail.probe_cardinality_before = before_probe;
		detail.build_distinct = build_distinct;
		detail.probe_distinct = probe_distinct;
		detail.survival = survival;
		detail.probe_cardinality_after = after_probe;
		if (!filter_reused) {
			// SJBuild materializes its input and later replays it as a source;
			// filter construction adds one more linear pass over the build keys.
			detail.materialize_cost =
			    cost_parameters.semijoin_materialize_weight * build_cardinality;
			detail.filter_build_cost =
			    cost_parameters.semijoin_filter_build_weight * build_cardinality;
			detail.replay_cost = cost_parameters.semijoin_replay_weight * build_cardinality;
			auto &build_cost = top_down ? summary.round2_build_cost : summary.round1_build_cost;
			build_cost += detail.materialize_cost + detail.filter_build_cost + detail.replay_cost;
		}
		// Probe inspects every input key and emits the survivors.
		detail.lookup_cost = cost_parameters.semijoin_probe_lookup_weight * before_probe;
		detail.emit_cost = cost_parameters.semijoin_probe_emit_weight * after_probe;
		auto &probe_cost = top_down ? summary.round2_probe_cost : summary.round1_probe_cost;
		probe_cost += detail.lookup_cost + detail.emit_cost;
		semijoin_cardinality[pair.probe] = after_probe;
		summary.semijoin_steps.push_back(std::move(detail));
	};

	for (auto &pair : tree.bottom_up_pairs) {
		process_pair(pair, false);
	}
	for (auto &pair : tree.top_down_pairs) {
		process_pair(pair, true);
	}
	summary.reduced_cardinalities = semijoin_cardinality;
}

void OuterYanDP::InitLeafPlans(OuterYanTree &tree) {
	for (idx_t i = 0; i < num_relations; i++) {
		auto &leaf_set = set_manager.GetJoinRelation(RelationIndex(i));
		auto node = make_uniq<DPJoinNode>(leaf_set);
		// The two reducer rounds are fixed query-global work. Charging them to
		// leaves would be redundant in exact DP and biases greedy comparisons
		// between different relation subsets.
		node->cost = 0.0;
		node->cardinality = static_cast<idx_t>(ClampPlanCardinality(semijoin_cardinality[i]));
		plans[leaf_set] = std::move(node);
	}
}

// ============================================================================
// DPccp enumeration (reorderability check dropped vs PlanEnumerator)
// ============================================================================

bool OuterYanDP::SolveExactly() {
	for (idx_t i = num_relations; i > 0; i--) {
		auto &start_node = set_manager.GetJoinRelation(RelationIndex(i - 1));
		if (!EmitCSG(start_node)) {
			return false;
		}
		unordered_set<RelationIndex> exclusion_set;
		for (idx_t j = 0; j < i; j++) {
			exclusion_set.emplace(RelationIndex(j));
		}
		if (!EnumerateCSGRecursive(start_node, exclusion_set)) {
			return false;
		}
	}
	return true;
}

bool OuterYanDP::EmitCSG(JoinRelationSet &node) {
	if (node.count == num_relations) {
		return true;
	}
	unordered_set<RelationIndex> exclusion_set;
	for (idx_t i = 0; i < node.relations[0].index; i++) {
		exclusion_set.emplace(RelationIndex(i));
	}
	UpdateExclusionSet(node, exclusion_set);
	auto neighbors = query_graph.GetNeighbors(node, exclusion_set);
	if (neighbors.empty()) {
		return true;
	}
	std::sort(neighbors.begin(), neighbors.end(), std::greater<RelationIndex>());

	unordered_set<RelationIndex> new_exclusion_set = exclusion_set;
	for (auto &nb : neighbors) {
		new_exclusion_set.insert(nb);
	}

	for (auto neighbor : neighbors) {
		auto &neighbor_relation = set_manager.GetJoinRelation(neighbor);
		auto connections = query_graph.GetConnections(node, neighbor_relation);
		if (!connections.empty()) {
			if (!TryEmitPair(node, neighbor_relation, connections)) {
				return false;
			}
		}
		if (!EnumerateCmpRecursive(node, neighbor_relation, new_exclusion_set)) {
			return false;
		}
		new_exclusion_set.erase(neighbor);
	}
	return true;
}

bool OuterYanDP::EnumerateCmpRecursive(JoinRelationSet &left, JoinRelationSet &right,
                                       unordered_set<RelationIndex> &exclusion_set) {
	auto neighbors = query_graph.GetNeighbors(right, exclusion_set);
	if (neighbors.empty()) {
		return true;
	}
	auto all_subset = GetAllNeighborSets(neighbors);
	vector<reference<JoinRelationSet>> union_sets;
	union_sets.reserve(all_subset.size());
	for (const auto &rel_set : all_subset) {
		auto &neighbor = set_manager.GetJoinRelation(rel_set);
		auto &combined = set_manager.Union(right, neighbor);
		if (plans.find(combined) != plans.end()) {
			auto connections = query_graph.GetConnections(left, combined);
			if (!connections.empty()) {
				if (!TryEmitPair(left, combined, connections)) {
					return false;
				}
			}
		}
		union_sets.push_back(combined);
	}
	unordered_set<RelationIndex> new_exclusion_set = exclusion_set;
	for (const auto &nb : neighbors) {
		new_exclusion_set.insert(nb);
	}
	for (idx_t i = 0; i < union_sets.size(); i++) {
		if (!EnumerateCmpRecursive(left, union_sets[i], new_exclusion_set)) {
			return false;
		}
	}
	return true;
}

bool OuterYanDP::EnumerateCSGRecursive(JoinRelationSet &node, unordered_set<RelationIndex> &exclusion_set) {
	auto neighbors = query_graph.GetNeighbors(node, exclusion_set);
	if (neighbors.empty()) {
		return true;
	}
	auto all_subset = GetAllNeighborSets(neighbors);
	vector<reference<JoinRelationSet>> union_sets;
	union_sets.reserve(all_subset.size());
	for (const auto &rel_set : all_subset) {
		auto &neighbor = set_manager.GetJoinRelation(rel_set);
		auto &new_set = set_manager.Union(node, neighbor);
		if (plans.find(new_set) != plans.end()) {
			if (!EmitCSG(new_set)) {
				return false;
			}
		}
		union_sets.push_back(new_set);
	}
	unordered_set<RelationIndex> new_exclusion_set = exclusion_set;
	for (const auto &nb : neighbors) {
		new_exclusion_set.insert(nb);
	}
	for (idx_t i = 0; i < union_sets.size(); i++) {
		if (!EnumerateCSGRecursive(union_sets[i], new_exclusion_set)) {
			return false;
		}
	}
	return true;
}

bool OuterYanDP::TryEmitPair(JoinRelationSet &left, JoinRelationSet &right,
                             const vector<reference<NeighborInfo>> &info) {
	auto &union_set = set_manager.Union(left, right);
	if (ViolatesRootFix(union_set)) {
		// Skip silently; the violating subset never enters the memo. Does not
		// count toward the pair cap since no real DP work was performed.
		return true;
	}
	pairs++;
	if (pairs >= MAX_PAIRS) {
		return false;
	}
	EmitPair(left, right, info);
	return true;
}

DPJoinNode &OuterYanDP::EmitPair(JoinRelationSet &left, JoinRelationSet &right,
                                 const vector<reference<NeighborInfo>> &info) {
	auto left_plan_it = plans.find(left);
	auto right_plan_it = plans.find(right);
	if (left_plan_it == plans.end() || right_plan_it == plans.end()) {
		throw InternalException("OuterYanDP::EmitPair: missing left/right plan");
	}
	auto &new_set = set_manager.Union(left, right);
	auto new_plan = CreateJoinTree(new_set, info, *left_plan_it->second, *right_plan_it->second);

	auto entry = plans.find(new_set);
	double new_cost = new_plan->cost;
	double old_cost = NumericLimits<double>::Maximum();
	if (entry != plans.end()) {
		old_cost = entry->second->cost;
	}
	if (entry == plans.end() || new_cost < old_cost) {
		plans[new_set] = std::move(new_plan);
		return *plans[new_set];
	}
	return *entry->second;
}

unique_ptr<DPJoinNode> OuterYanDP::CreateJoinTree(JoinRelationSet &set,
                                                  const vector<reference<NeighborInfo>> &possible_connections,
                                                  DPJoinNode &left, DPJoinNode &right) {
	// OuterYan applicability guarantees an acyclic predicate graph: there is
	// at most one OT JOIN connecting any partition cut, so the first non-null
	// FilterInfo is the answer.
	optional_ptr<NeighborInfo> best_connection = possible_connections.back().get();
	optional_ptr<FilterInfo> chosen_filter;
	for (auto &connection : possible_connections) {
		for (auto &filter : connection.get().filters) {
			if (filter) {
				best_connection = connection.get();
				chosen_filter = filter;
				break;
			}
		}
		if (chosen_filter) {
			break;
		}
	}
	if (!chosen_filter) {
		throw InternalException("OuterYanDP::CreateJoinTree: no non-cross-product connection found");
	}
	auto fi_idx = chosen_filter->filter_index;
	if (fi_idx >= ot_joins_by_filter_index.size() || !ot_joins_by_filter_index[fi_idx] ||
	    !ot_joins_by_filter_index[fi_idx]->info) {
		throw InternalException("OuterYanDP::CreateJoinTree: missing OTJoin for filter_index %llu",
		                        fi_idx);
	}
	const auto &join_info = *ot_joins_by_filter_index[fi_idx]->info;

	auto estimate = EdgeCardinality(left.set, right.set, left, right, join_info);
	double cost = ComputeCost(left, right, estimate);

	auto result = make_uniq<DPJoinNode>(set, best_connection, left.set, right.set, cost);
	result->cardinality = static_cast<idx_t>(ClampPlanCardinality(estimate.output));
	return result;
}

// ============================================================================
// Cost (user's outer-join formula)
// ============================================================================

OuterYanDP::JoinEstimate OuterYanDP::EdgeCardinality(JoinRelationSet &left_set, JoinRelationSet &right_set,
                                                     const DPJoinNode &left_plan, const DPJoinNode &right_plan,
                                                     const OTJoin &info) const {
	bool left_holds_lhs = false;
	for (idx_t i = 0; i < left_set.count; i++) {
		if (left_set.relations[i].index == info.cond_left_relation_id) {
			left_holds_lhs = true;
			break;
		}
	}
	if (!left_holds_lhs) {
		bool right_holds_lhs = false;
		for (idx_t i = 0; i < right_set.count; i++) {
			if (right_set.relations[i].index == info.cond_left_relation_id) {
				right_holds_lhs = true;
				break;
			}
		}
		if (!right_holds_lhs) {
			throw InternalException("OuterYanDP::EdgeCardinality: edge LHS relation absent from both sides");
		}
	}

	const double left_distinct = left_holds_lhs ? info.left_distinct_count : info.right_distinct_count;
	const double right_distinct = left_holds_lhs ? info.right_distinct_count : info.left_distinct_count;
	const auto kind = left_holds_lhs ? info.join_kind : FlipOuterYanJoinKind(info.join_kind);
	return EstimateJoin(static_cast<double>(left_plan.cardinality), static_cast<double>(right_plan.cardinality),
	                    left_distinct, right_distinct, kind);
}

OuterYanDP::JoinEstimate OuterYanDP::EstimateJoin(double left_cardinality, double right_cardinality,
                                                  double left_distinct, double right_distinct,
                                                  OuterYanJoinKind kind) const {
	JoinEstimate estimate;
	if (left_cardinality == 0.0 || right_cardinality == 0.0) {
		estimate.unmatched_left = right_cardinality == 0.0 ? left_cardinality : 0.0;
		estimate.unmatched_right = left_cardinality == 0.0 ? right_cardinality : 0.0;
		switch (kind) {
		case JoinType::INNER:
			estimate.output = 0.0;
			break;
		case JoinType::LEFT:
			estimate.output = estimate.unmatched_left;
			estimate.weighted_output_cost =
			    cost_parameters.unmatched_left_weight * estimate.unmatched_left;
			break;
		case JoinType::RIGHT:
			estimate.output = estimate.unmatched_right;
			estimate.weighted_output_cost =
			    cost_parameters.unmatched_right_weight * estimate.unmatched_right;
			break;
		case JoinType::OUTER:
			estimate.output = estimate.unmatched_left + estimate.unmatched_right;
			estimate.weighted_output_cost =
			    cost_parameters.unmatched_left_weight * estimate.unmatched_left +
			    cost_parameters.unmatched_right_weight * estimate.unmatched_right;
			break;
		default:
			throw InternalException("OuterYanDP::EstimateJoin: unsupported join kind");
		}
		return estimate;
	}
	const double d_l = MinValue<double>(left_cardinality, MaxValue<double>(left_distinct, 1.0));
	const double d_r = MinValue<double>(right_cardinality, MaxValue<double>(right_distinct, 1.0));
	estimate.inner = (left_cardinality * right_cardinality) / MaxValue<double>(d_l, d_r);

	const double p_l_not_r = MaxValue<double>(0.0, 1.0 - MinValue<double>(1.0, d_r / d_l));
	const double p_r_not_l = MaxValue<double>(0.0, 1.0 - MinValue<double>(1.0, d_l / d_r));
	estimate.unmatched_left = left_cardinality * p_l_not_r;
	estimate.unmatched_right = right_cardinality * p_r_not_l;
	estimate.weighted_output_cost = cost_parameters.inner_output_weight * estimate.inner;

	switch (kind) {
	case JoinType::INNER:
		estimate.output = estimate.inner;
		break;
	case JoinType::LEFT:
		estimate.output = estimate.inner + estimate.unmatched_left;
		estimate.weighted_output_cost += cost_parameters.unmatched_left_weight * estimate.unmatched_left;
		break;
	case JoinType::RIGHT:
		estimate.output = estimate.inner + estimate.unmatched_right;
		estimate.weighted_output_cost += cost_parameters.unmatched_right_weight * estimate.unmatched_right;
		break;
	case JoinType::OUTER:
		estimate.output = estimate.inner + estimate.unmatched_left + estimate.unmatched_right;
		estimate.weighted_output_cost += cost_parameters.unmatched_left_weight * estimate.unmatched_left +
		                                 cost_parameters.unmatched_right_weight * estimate.unmatched_right;
		break;
	default:
		throw InternalException("OuterYanDP::EstimateJoin: unsupported join kind");
	}
	return estimate;
}

double OuterYanDP::ComputeCost(const DPJoinNode &left, const DPJoinNode &right,
                               const JoinEstimate &estimate) const {
	// Same cumulative shape as DuckDB's CostModel: child costs plus the
	// estimated output work of this join. Join type is already reflected in the
	// weighted output components.
	return left.cost + right.cost + estimate.weighted_output_cost;
}

double OuterYanDP::ClampPlanCardinality(double cardinality) {
	if (!std::isfinite(cardinality) || cardinality < 0.0) {
		return 1.0;
	}
	if (cardinality == 0.0) {
		return 0.0;
	}
	if (cardinality <= 1.0) {
		return 1.0;
	}
	const double max_cardinality = static_cast<double>(NumericLimits<idx_t>::Maximum());
	if (cardinality >= max_cardinality) {
		return max_cardinality;
	}
	return static_cast<double>(static_cast<idx_t>(cardinality));
}

OuterYanDP::JoinTreeEstimate OuterYanDP::ScoreCurrentJoinTreeNode(
    const OuterYanTree &tree, const OTNode &node, const vector<double> *leaf_cardinality_override,
    vector<OuterYanJoinCostStep> *steps) const {
	if (node.kind == OTNode::Kind::RELATION) {
		JoinTreeEstimate leaf;
		if (leaf_cardinality_override) {
			if (node.relation_id >= leaf_cardinality_override->size()) {
				throw InternalException("OuterYanDP::ScoreCurrentJoinTree: leaf override missing relation %llu",
				                        node.relation_id);
			}
			leaf.cardinality = ClampPlanCardinality((*leaf_cardinality_override)[node.relation_id]);
		} else if (node.stats.stats_initialized) {
			leaf.cardinality = static_cast<double>(node.stats.cardinality);
		} else {
			leaf.cardinality = static_cast<double>(MaxValue<idx_t>(node.stats.cardinality, 1));
		}
		return leaf;
	}
	if (!node.info || !node.children[0] || !node.children[1]) {
		throw InternalException("OuterYanDP::ScoreCurrentJoinTree: malformed JOIN node");
	}

	auto left = ScoreCurrentJoinTreeNode(tree, *node.children[0], leaf_cardinality_override, steps);
	auto right = ScoreCurrentJoinTreeNode(tree, *node.children[1], leaf_cardinality_override, steps);
	const auto &info = *node.info;
	const bool lhs_in_left = node.children[0]->subtree_relations.count(info.cond_left_relation_id) != 0;
	const bool rhs_in_right = node.children[1]->subtree_relations.count(info.cond_right_relation_id) != 0;
	const bool lhs_in_right = node.children[1]->subtree_relations.count(info.cond_left_relation_id) != 0;
	const bool rhs_in_left = node.children[0]->subtree_relations.count(info.cond_right_relation_id) != 0;
	if ((!lhs_in_left || !rhs_in_right) && (!lhs_in_right || !rhs_in_left)) {
		throw InternalException("OuterYanDP::ScoreCurrentJoinTree: JOIN condition does not cross its children");
	}

	const double left_distinct = lhs_in_left ? info.left_distinct_count : info.right_distinct_count;
	const double right_distinct = lhs_in_left ? info.right_distinct_count : info.left_distinct_count;
	// `info.join_kind` is children-relative in an actual OT. Only the condition
	// side statistics need swapping when its bindings are reversed.
	auto estimate = EstimateJoin(left.cardinality, right.cardinality, left_distinct, right_distinct, info.join_kind);
	JoinTreeEstimate result;
	result.cardinality = ClampPlanCardinality(estimate.output);
	result.cost = left.cost + right.cost + estimate.weighted_output_cost;
	if (steps) {
		OuterYanJoinCostStep detail;
		detail.step = steps->size() + 1;
		detail.join_kind = info.join_kind;
		detail.left_table_indexes = StableTableIndexes(tree, node.children[0]->subtree_relations);
		detail.right_table_indexes = StableTableIndexes(tree, node.children[1]->subtree_relations);
		detail.output_table_indexes = StableTableIndexes(tree, node.subtree_relations);
		detail.left_cardinality = left.cardinality;
		detail.right_cardinality = right.cardinality;
		detail.left_distinct = left_distinct;
		detail.right_distinct = right_distinct;
		detail.inner = estimate.inner;
		detail.unmatched_left = estimate.unmatched_left;
		detail.unmatched_right = estimate.unmatched_right;
		detail.output = result.cardinality;
		detail.local_cost = estimate.weighted_output_cost;
		detail.subtree_cost = result.cost;
		steps->push_back(std::move(detail));
	}
	return result;
}

double OuterYanDP::ScoreCurrentJoinTree(OuterYanTree &tree) {
	return ScoreCurrentJoinTreeDetailed(tree).total_cost;
}

OuterYanJoinCostBreakdown OuterYanDP::ScoreCurrentJoinTreeDetailed(
    OuterYanTree &tree, const vector<double> *leaf_cardinality_override) {
	if (!tree.HasOT()) {
		throw InternalException("OuterYanDP::ScoreCurrentJoinTree: tree.ot is null");
	}
	BuildLeafRelations(tree);
	BuildEdgeStatistics(tree);
	if (leaf_cardinality_override && leaf_cardinality_override->size() != tree.ot_relations_by_id.size()) {
		throw InternalException("OuterYanDP::ScoreCurrentJoinTree: expected %llu leaf overrides, got %llu",
		                        tree.ot_relations_by_id.size(), leaf_cardinality_override->size());
	}
	OuterYanJoinCostBreakdown result;
	auto root = ScoreCurrentJoinTreeNode(tree, tree.OT().Root(), leaf_cardinality_override, &result.steps);
	result.root_cardinality = root.cardinality;
	result.total_cost = root.cost;
	return result;
}

// ============================================================================
// Greedy fallback (no cross products)
// ============================================================================

bool OuterYanDP::SolveApproximately() {
	pairs = 0;
	vector<reference<JoinRelationSet>> live;
	for (idx_t i = 0; i < num_relations; i++) {
		live.push_back(set_manager.GetJoinRelation(RelationIndex(i)));
	}

	while (live.size() > 1) {
		idx_t best_left = 0, best_right = 0;
		optional_ptr<DPJoinNode> best_node;

		for (idx_t i = 0; i < live.size(); i++) {
			auto &l = live[i].get();
			for (idx_t j = i + 1; j < live.size(); j++) {
				auto &r = live[j].get();
				auto connections = query_graph.GetConnections(l, r);
				if (connections.empty()) {
					continue;
				}
				auto &candidate_set = set_manager.Union(l, r);
				if (ViolatesRootFix(candidate_set)) {
					// Forbidden union under the active root-fix regime;
					// skip without recording a memo entry.
					continue;
				}
				auto &candidate = EmitPair(l, r, connections);
				if (!best_node || candidate.cost < best_node->cost) {
					best_node = &candidate;
					best_left = i;
					best_right = j;
				}
			}
		}

		if (!best_node) {
			// No non-cross-product connection -- Path A bail-out.
			bailed_out = true;
			return false;
		}

		auto &new_set = set_manager.Union(live[best_left].get(), live[best_right].get());
		live.erase(live.begin() + static_cast<int64_t>(best_right));
		live.erase(live.begin() + static_cast<int64_t>(best_left));
		live.push_back(new_set);
	}
	return true;
}

// ============================================================================
// Materialisation -- DP plan back to OT
// ============================================================================

const FilterInfo &OuterYanDP::PickConnectingEdge(const DPJoinNode &node) {
	if (!node.info) {
		throw InternalException("OuterYanDP::PickConnectingEdge: leaf DPJoinNode");
	}
	for (auto &filter : node.info->filters) {
		if (filter) {
			return *filter;
		}
	}
	throw InternalException("OuterYanDP::PickConnectingEdge: NeighborInfo has no filter");
}

unique_ptr<OTNode> OuterYanDP::MaterializeNode(JoinRelationSet &set, OuterYanTree &tree, idx_t &next_order) {
	auto plan_it = plans.find(set);
	if (plan_it == plans.end()) {
		throw InternalException("OuterYanDP::MaterializeNode: no plan for set %s", set.ToString());
	}
	auto &node = *plan_it->second;

	if (set.count == 1) {
		// Leaf: clone the original RELATION OTNode. The base-op pointer and stats
		// are kept; subtree_relations is repopulated by Finalize. PK-FK side is no
		// longer cached per relation — it is derived per join edge from the join
		// columns in attach_edge (see JoinSideIsUnique).
		auto rel_id = set.relations[0].index;
		auto *src = tree.ot_relations_by_id[rel_id];
		auto leaf = make_uniq<OTNode>();
		leaf->kind = OTNode::Kind::RELATION;
		leaf->origin = src->origin;
		leaf->relation_id = rel_id;
		leaf->stats = src->stats;
		return leaf;
	}

	auto left_child = MaterializeNode(node.left_set, tree, next_order);
	auto right_child = MaterializeNode(node.right_set, tree, next_order);

	const auto &chosen_filter = PickConnectingEdge(node);
	auto fi_idx = chosen_filter.filter_index;
	if (fi_idx >= ot_joins_by_filter_index.size() || !ot_joins_by_filter_index[fi_idx]) {
		throw InternalException("OuterYanDP::MaterializeNode: missing OTJoin for filter_index %llu",
		                        fi_idx);
	}
	auto *origin_join = ot_joins_by_filter_index[fi_idx];
	if (!origin_join->info) {
		throw InternalException("OuterYanDP::MaterializeNode: OT JOIN's info already moved");
	}

	auto join = make_uniq<OTNode>();
	join->kind = OTNode::Kind::JOIN;
	// Transfer ownership of the OTJoin payload to the new node. The old OT
	// JOIN OTNode becomes inert; it will be destroyed when RebuildOT swaps
	// the OT root.
	join->info = std::move(origin_join->info);
	join->children[0] = std::move(left_child);
	join->children[1] = std::move(right_child);
	join->order = ++next_order;

	// `join_kind` is children-relative (BuildOJT reads it as "children[0]
	// preserved" via `parent_is_left`). The moved payload is oriented to the
	// join's canonical layout — cond-LHS relation in children[0] — but the DP
	// may have placed the operands swapped. If the chosen `left_set` does NOT
	// hold the cond-LHS relation, flip LEFT<->RIGHT on the persisted kinds so
	// the SAME relation stays preserved (no-op for INNER/FULL). This mirrors the
	// `left_holds_lhs` flip in EdgeCardinality, which previously applied it only
	// to the cost formula and never to the materialised tree.
	bool left_holds_lhs = false;
	for (idx_t i = 0; i < node.left_set.count; i++) {
		if (node.left_set.relations[i].index == join->info->cond_left_relation_id) {
			left_holds_lhs = true;
			break;
		}
	}
	if (!left_holds_lhs) {
		join->info->join_kind = FlipOuterYanJoinKind(join->info->join_kind);
		join->info->original_join_kind = FlipOuterYanJoinKind(join->info->original_join_kind);
	}
	return join;
}

void OuterYanDP::RebuildOT(OuterYanTree &tree, JoinRelationSet &full_set) {
	idx_t next_order = 0;
	auto new_root = MaterializeNode(full_set, tree, next_order);

	tree.OT().root = std::move(new_root);
	// Re-canonicalise (cond LHS/RHS aligned with new children's subtree_relations)
	// and re-populate subtree_relations.
	tree.OT().Finalize();

	tree.ot_relations_by_id.assign(num_relations, nullptr);
	RefreshOTRelationsById(*tree.OT().root, tree.ot_relations_by_id);
	tree.ot_joins_by_order.clear();
	RefreshOTJoinsByOrder(*tree.OT().root, tree.ot_joins_by_order);
	// Renumber `order` densely after Finalize; MaterializeNode produced
	// post-order numbering but Finalize may have left it stale.
	for (idx_t i = 0; i < tree.ot_joins_by_order.size(); i++) {
		tree.ot_joins_by_order[i]->order = i + 1;
	}
}

void OuterYanDP::RefreshOTRelationsById(OTNode &node, vector<OTNode *> &out) {
	if (node.kind == OTNode::Kind::RELATION) {
		if (node.relation_id >= out.size() || out[node.relation_id]) {
			throw InternalException("OuterYanDP: invalid rebuilt relation id %llu", node.relation_id);
		}
		out[node.relation_id] = &node;
		return;
	}
	RefreshOTRelationsById(*node.children[0], out);
	RefreshOTRelationsById(*node.children[1], out);
}

OuterYanDP::JoinGroupingTableSignature OuterYanDP::JoinGroupingSignature(const OuterYanTree &tree) {
	JoinGroupingTableSignature signature;
	for (auto *jn : tree.ot_joins_by_order) {
		if (!jn || jn->kind != OTNode::Kind::JOIN) {
			continue;
		}
		vector<idx_t> tables;
		for (const auto &entry : tree.table_to_relation) {
			if (jn->subtree_relations.count(entry.second) != 0) {
				tables.push_back(entry.first);
			}
		}
		if (tables.empty() && !jn->subtree_relations.empty()) {
			throw InternalException("OuterYanDP::JoinGroupingSignature: JOIN subtree has no mapped tables");
		}
		std::sort(tables.begin(), tables.end());
		tables.erase(std::unique(tables.begin(), tables.end()), tables.end());
		signature.insert(std::move(tables));
	}
	return signature;
}

vector<idx_t> OuterYanDP::StableTableIndexes(const OuterYanTree &tree,
                                             const unordered_set<idx_t> &relations) {
	vector<idx_t> tables;
	for (const auto &entry : tree.table_to_relation) {
		if (relations.count(entry.second) != 0) {
			tables.push_back(entry.first);
		}
	}
	if (tables.empty() && !relations.empty()) {
		throw InternalException("OuterYanDP: relation set has no stable table mapping");
	}
	std::sort(tables.begin(), tables.end());
	tables.erase(std::unique(tables.begin(), tables.end()), tables.end());
	return tables;
}

idx_t OuterYanDP::StableTableIndex(const OuterYanTree &tree, idx_t relation_id) {
	idx_t result = DConstants::INVALID_INDEX;
	for (const auto &entry : tree.table_to_relation) {
		if (entry.second != relation_id) {
			continue;
		}
		if (result == DConstants::INVALID_INDEX || entry.first < result) {
			result = entry.first;
		}
	}
	if (result == DConstants::INVALID_INDEX) {
		throw InternalException("OuterYanDP: relation %llu has no stable table mapping", relation_id);
	}
	return result;
}

// ============================================================================
// Static private helpers
// ============================================================================

LogicalOperator *OuterYanDP::FindBaseGet(LogicalOperator *op) {
	while (op) {
		if (op->type == LogicalOperatorType::LOGICAL_FILTER ||
		    op->type == LogicalOperatorType::LOGICAL_PROJECTION) {
			if (op->children.size() != 1 || !op->children[0]) {
				return op;
			}
			op = op->children[0].get();
			continue;
		}
		return op;
	}
	return nullptr;
}

optional_ptr<const BoundColumnRefExpression> OuterYanDP::FirstColumnRef(const Expression &expr) {
	if (expr.GetExpressionClass() == ExpressionClass::BOUND_COLUMN_REF) {
		return &expr.Cast<BoundColumnRefExpression>();
	}
	optional_ptr<const BoundColumnRefExpression> result;
	ExpressionIterator::EnumerateChildren(expr, [&](const Expression &child) {
		if (!result) {
			result = FirstColumnRef(child);
		}
	});
	return result;
}

idx_t OuterYanDP::LookupDistinctCount(const RelationStats &stats, idx_t column_index) {
	if (!stats.stats_initialized) {
		return 1;
	}
	if (stats.cardinality == 0) {
		return 0;
	}
	if (column_index >= stats.column_distinct_count.size()) {
		return MaxValue<idx_t>(stats.cardinality, 1);
	}
	auto dc = stats.column_distinct_count[column_index].distinct_count;
	return MaxValue<idx_t>(dc, 1);
}

void OuterYanDP::UpdateExclusionSet(JoinRelationSet &node, unordered_set<RelationIndex> &exclusion_set) {
	for (idx_t i = 0; i < node.count; i++) {
		exclusion_set.insert(node.relations[i]);
	}
}

vector<unordered_set<RelationIndex>>
OuterYanDP::AddSuperSets(const vector<unordered_set<RelationIndex>> &current,
                          const vector<RelationIndex> &all_neighbors) {
	vector<unordered_set<RelationIndex>> ret;
	for (const auto &neighbor_set : current) {
		auto max_val = std::max_element(neighbor_set.begin(), neighbor_set.end());
		for (const auto &neighbor : all_neighbors) {
			if (*max_val >= neighbor) {
				continue;
			}
			if (neighbor_set.count(neighbor) == 0) {
				unordered_set<RelationIndex> new_set;
				for (auto &n : neighbor_set) {
					new_set.insert(n);
				}
				new_set.insert(neighbor);
				ret.push_back(std::move(new_set));
			}
		}
	}
	return ret;
}

vector<unordered_set<RelationIndex>> OuterYanDP::GetAllNeighborSets(vector<RelationIndex> neighbors) {
	vector<unordered_set<RelationIndex>> ret;
	std::sort(neighbors.begin(), neighbors.end());
	vector<unordered_set<RelationIndex>> added;
	for (auto &neighbor : neighbors) {
		added.push_back(unordered_set<RelationIndex>({neighbor}));
		ret.push_back(unordered_set<RelationIndex>({neighbor}));
	}
	do {
		added = AddSuperSets(added, neighbors);
		for (auto &d : added) {
			ret.push_back(d);
		}
	} while (!added.empty());
	return ret;
}

void OuterYanDP::RefreshOTJoinsByOrder(OTNode &node, vector<OTNode *> &out) {
	if (node.kind != OTNode::Kind::JOIN) {
		return;
	}
	RefreshOTJoinsByOrder(*node.children[0], out);
	RefreshOTJoinsByOrder(*node.children[1], out);
	out.push_back(&node);
}

} // namespace duckdb
