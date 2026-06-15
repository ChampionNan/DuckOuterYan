#include "duckdb/optimizer/outer_yan/common/ordered_join_tree.hpp"

#include "duckdb/catalog/catalog_entry/table_catalog_entry.hpp"
#include "duckdb/common/enum_util.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/string_util.hpp"
#include "duckdb/planner/operator/logical_get.hpp"

#include <algorithm>
#include <sstream>

namespace duckdb {

OrderedJoinTree::OrderedJoinTree() = default;

OrderedJoinTree::OrderedJoinTree(unique_ptr<OJTNode> root_p) : root(std::move(root_p)) {
}

void OrderedJoinTree::PostOrder(std::function<void(OJTNode &, optional_ptr<OJTNode>, OuterYanJoinKind)> callback) {
	throw NotImplementedException("OrderedJoinTree::PostOrder");
}

// ============================================================================
// Printer helpers
// ============================================================================

string OrderedJoinTree::RelationLabel(const OJTNode &node) {
	const auto *base = FindBaseOp(node.base_op);
	if (!base) {
		return "<no base_op>";
	}
	if (base->type == LogicalOperatorType::LOGICAL_GET) {
		auto &get = base->Cast<LogicalGet>();
		auto table_entry = get.GetTable();
		string name = table_entry ? table_entry->name : "<no_table>";
		return StringUtil::Format("%s [table_index=%llu]", name.c_str(), get.table_index.index);
	}
	return EnumUtil::ToString(base->type);
}

void OrderedJoinTree::CollectNodes(const OJTNode &node, vector<const OJTNode *> &out) {
	out.push_back(&node);
	for (const auto &edge : node.children) {
		if (edge.child) {
			CollectNodes(*edge.child, out);
		}
	}
}

void OrderedJoinTree::CollectEdges(const OJTNode &node, vector<const OJTEdge *> &out) {
	for (const auto &edge : node.children) {
		if (!edge.child) {
			continue;
		}
		out.push_back(&edge);
		CollectEdges(*edge.child, out);
	}
}

// Directional connector for a "parent KIND child" edge. The arrow points FROM
// the preserved operand TOWARD the null-extended one:
//   LEFT  (parent preserved)  -> ;  RIGHT (child preserved)  <- ;
//   FULL  (both preserved)    <->;  INNER (neither)          ⋈ .
static const char *JoinSymbol(OuterYanJoinKind kind) {
	switch (kind) {
	case JoinType::INNER:
		return " ⋈ ";
	case JoinType::LEFT:
		return " -> ";
	case JoinType::RIGHT:
		return " <- ";
	case JoinType::OUTER:
		return " <-> ";
	default:
		return " ?? ";
	}
}

unordered_map<idx_t, string> OrderedJoinTree::BuildAlias(const OJTNode &root) {
	vector<const OJTNode *> nodes;
	CollectNodes(root, nodes);
	unordered_map<idx_t, string> alias;
	for (auto *n : nodes) {
		const auto *base = FindBaseOp(n->base_op);
		if (base && base->type == LogicalOperatorType::LOGICAL_GET) {
			auto te = base->Cast<LogicalGet>().GetTable();
			alias[n->relation_id] = te ? te->name : StringUtil::Format("R%llu", n->relation_id);
		} else {
			alias[n->relation_id] = StringUtil::Format("R%llu", n->relation_id);
		}
	}
	return alias;
}

void OrderedJoinTree::PrintNodeRecursive(const OJTNode &node, std::ostringstream &os,
                                         const string &indent, bool is_last_child, bool is_root,
                                         const OJTEdge *incoming_edge, bool verbose,
                                         const unordered_map<idx_t, string> &alias) {
	auto name_of = [&alias](idx_t rel) -> string {
		auto it = alias.find(rel);
		return it != alias.end() ? it->second : StringUtil::Format("R%llu", rel);
	};
	os << indent;
	if (!is_root && incoming_edge) {
		os << (is_last_child ? "└──" : "├──");
		os << "[order=" << incoming_edge->order << ", " << EnumUtil::ToString(incoming_edge->kind);
		if (verbose) {
			// Which relation joins which: parent <dir> child, the arrow marking
			// the preserved side; then de-simplification / PK / elim flags.
			os << ": " << name_of(incoming_edge->parent_relation_id)
			   << JoinSymbol(incoming_edge->kind) << name_of(node.relation_id);
			if (incoming_edge->original_kind != incoming_edge->kind) {
				os << " was=" << EnumUtil::ToString(incoming_edge->original_kind);
			}
			if (incoming_edge->has_pk_fk_constraint) {
				os << (incoming_edge->child_is_pk ? " pk=child" : " pk=parent");
			}
			if (incoming_edge->bottom_up_eliminated) {
				os << " bu-elim";
			}
			if (incoming_edge->top_down_eliminated) {
				os << " td-elim";
			}
		}
		os << "]── ";
	}
	os << RelationLabel(node);
	if (verbose) {
		os << " rel=" << node.relation_id;
	}
	if (!node.filters.empty()) {
		os << " filters=" << node.filters.size();
	}
	os << "\n";

	string child_indent = indent;
	if (!is_root) {
		child_indent += (is_last_child ? "    " : "│   ");
	}
	for (idx_t i = 0; i < node.children.size(); i++) {
		const auto &edge = node.children[i];
		if (!edge.child) {
			continue;
		}
		bool last = (i + 1 == node.children.size());
		PrintNodeRecursive(*edge.child, os, child_indent, last, false, &edge, verbose, alias);
	}
}

// ============================================================================
// Printers
// ============================================================================

string OrderedJoinTree::Print() const {
	std::ostringstream os;
	const auto &r = Root();

	vector<const OJTNode *> nodes;
	CollectNodes(r, nodes);
	std::sort(nodes.begin(), nodes.end(),
	          [](const OJTNode *a, const OJTNode *b) { return a->relation_id < b->relation_id; });

	vector<const OJTEdge *> edges;
	CollectEdges(r, edges);
	std::sort(edges.begin(), edges.end(),
	          [](const OJTEdge *a, const OJTEdge *b) { return a->order < b->order; });

	// Short alias map for edge reference labels
	unordered_map<idx_t, string> alias;
	for (auto *n : nodes) {
		const auto *base = FindBaseOp(n->base_op);
		if (base && base->type == LogicalOperatorType::LOGICAL_GET) {
			auto &get = base->Cast<LogicalGet>();
			auto te = get.GetTable();
			alias[n->relation_id] = te ? te->name : "<no_table>";
		} else {
			alias[n->relation_id] = StringUtil::Format("R%llu", n->relation_id);
		}
	}

	os << "OJT: " << nodes.size() << " relations, " << edges.size() << " joins\n";
	os << "root: " << alias[r.relation_id] << "\n";
	os << "relations:\n";
	for (auto *n : nodes) {
		os << "  " << RelationLabel(*n);
		if (!n->filters.empty()) {
			os << " (filters=" << n->filters.size() << ")";
		}
		os << "\n";
	}
	os << "edges (parent --KIND/order--> child):\n";
	for (auto *e : edges) {
		os << "  " << alias[e->parent_relation_id] << " --" << EnumUtil::ToString(e->kind) << "/" << e->order
		   << "--> " << alias[e->child->relation_id] << "\n";
	}
	return os.str();
}

string OrderedJoinTree::PrintAsTree(bool verbose) const {
	std::ostringstream os;
	const auto &r = Root();

	vector<const OJTNode *> nodes;
	CollectNodes(r, nodes);
	vector<const OJTEdge *> edges;
	CollectEdges(r, edges);
	auto alias = BuildAlias(r);
	os << "OJT (" << nodes.size() << " relations, " << edges.size() << " joins)\n";
	PrintNodeRecursive(r, os, /*indent*/ "", /*is_last_child*/ true, /*is_root*/ true,
	                   /*incoming_edge*/ nullptr, verbose, alias);
	return os.str();
}

} // namespace duckdb
