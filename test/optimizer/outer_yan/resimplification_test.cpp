#include "catch.hpp"

#include "duckdb/optimizer/outer_yan/pipeline/resimplification.hpp"
#include "duckdb/planner/expression/bound_columnref_expression.hpp"

using namespace duckdb;

namespace {

unique_ptr<OJTNode> SimplicityNode(idx_t relation) {
	auto node = make_uniq<OJTNode>();
	node->relation_id = relation;
	return node;
}

void AddSimplicityEdge(OJTNode &parent, unique_ptr<OJTNode> child, JoinType kind, idx_t order,
                       JoinType original) {
	OJTEdge edge;
	edge.parent_relation_id = parent.relation_id;
	edge.kind = kind;
	edge.original_kind = original;
	edge.order = order;
	edge.info = make_uniq<OTJoin>();
	edge.info->join_kind = kind;
	edge.info->original_join_kind = original;
	edge.info->cond_left_relation_id = parent.relation_id;
	edge.info->cond_right_relation_id = child->relation_id;
	edge.info->conditions.emplace_back(
	    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER,
	                                       ColumnBinding(TableIndex(parent.relation_id), ProjectionIndex(0))),
	    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER,
	                                       ColumnBinding(TableIndex(child->relation_id), ProjectionIndex(0))),
	    ExpressionType::COMPARE_EQUAL);
	edge.child = std::move(child);
	parent.children.push_back(std::move(edge));
}

} // namespace

TEST_CASE("outer_yan resimplification: all two-join preservation combinations", "[outer_yan][resimplify]") {
	const vector<JoinType> kinds {JoinType::INNER, JoinType::LEFT, JoinType::RIGHT, JoinType::OUTER};
	for (const auto lower : kinds) {
		for (const auto upper : kinds) {
			// The same rooted star can encode left-deep or right-deep binary
			// expressions: input groups are assembled by order, not traversal.
			auto root = SimplicityNode(0);
			AddSimplicityEdge(*root, SimplicityNode(1), lower, 1, lower);
			AddSimplicityEdge(*root, SimplicityNode(2), upper, 2, upper);
			OrderedJoinTree tree(std::move(root));
			const bool root_padded = lower == JoinType::RIGHT || lower == JoinType::OUTER;
			const bool root_rejected = upper == JoinType::INNER || upper == JoinType::RIGHT;
			CAPTURE(static_cast<int>(lower), static_cast<int>(upper));
			REQUIRE(Resimplification::IsSimple(tree) == !(root_padded && root_rejected));
		}
	}
}

TEST_CASE("outer_yan resimplification: rejects restoration through NULL-padded input",
          "[outer_yan][resimplify]") {
	// ((R0 RIGHT R1) LEFT R2) FULL R3, all predicates on R0.
	// The later FULL has the required arrow, but restoring the middle LEFT
	// to INNER would reject NULL R0 tuples introduced by the first RIGHT.
	auto root = SimplicityNode(0);
	AddSimplicityEdge(*root, SimplicityNode(1), JoinType::RIGHT, 1, JoinType::RIGHT);
	AddSimplicityEdge(*root, SimplicityNode(2), JoinType::LEFT, 2, JoinType::INNER);
	AddSimplicityEdge(*root, SimplicityNode(3), JoinType::OUTER, 3, JoinType::OUTER);
	OrderedJoinTree tree(std::move(root));
	REQUIRE(Resimplification::IsSimple(tree));
	Resimplification pass;
	pass.Apply(tree);
	REQUIRE(pass.reverts == 0);
	REQUIRE(tree.Root().children[1].kind == JoinType::LEFT);
	REQUIRE(tree.Root().children[1].original_kind == JoinType::INNER);
	REQUIRE(Resimplification::IsSimple(tree));
}

TEST_CASE("outer_yan resimplification: safe restoration keeps original snapshot", "[outer_yan][resimplify]") {
	auto root = SimplicityNode(0);
	AddSimplicityEdge(*root, SimplicityNode(1), JoinType::LEFT, 1, JoinType::INNER);
	AddSimplicityEdge(*root, SimplicityNode(2), JoinType::RIGHT, 2, JoinType::RIGHT);
	OrderedJoinTree tree(std::move(root));
	Resimplification pass;
	pass.Apply(tree);
	REQUIRE(pass.reverts == 1);
	REQUIRE(tree.Root().children[0].kind == JoinType::INNER);
	REQUIRE(tree.Root().children[0].original_kind == JoinType::INNER);
	REQUIRE(Resimplification::IsSimple(tree));
	pass.Apply(tree);
	REQUIRE(pass.reverts == 0);
}

TEST_CASE("outer_yan resimplification: missing arrow does not authorize restoration", "[outer_yan][resimplify]") {
	auto root = SimplicityNode(0);
	AddSimplicityEdge(*root, SimplicityNode(1), JoinType::LEFT, 1, JoinType::INNER);
	// LEFT targets R2, not the shared R0.
	AddSimplicityEdge(*root, SimplicityNode(2), JoinType::LEFT, 2, JoinType::LEFT);
	OrderedJoinTree tree(std::move(root));
	Resimplification pass;
	pass.Apply(tree);
	REQUIRE(pass.reverts == 0);
	REQUIRE(tree.Root().children[0].kind == JoinType::LEFT);
}

TEST_CASE("outer_yan resimplification: restores both one-sided outer orientations", "[outer_yan][resimplify]") {
	for (const auto original : {JoinType::LEFT, JoinType::RIGHT}) {
		auto root = SimplicityNode(0);
		AddSimplicityEdge(*root, SimplicityNode(1), JoinType::OUTER, 1, original);
		AddSimplicityEdge(*root, SimplicityNode(2), JoinType::OUTER, 2, JoinType::OUTER);
		OrderedJoinTree tree(std::move(root));
		Resimplification pass;
		pass.Apply(tree);
		REQUIRE(pass.reverts == 1);
		REQUIRE(tree.Root().children[0].kind == original);
		REQUIRE(tree.Root().children[0].original_kind == original);
		REQUIRE(Resimplification::IsSimple(tree));
	}
}

TEST_CASE("outer_yan resimplification: checks NULL padding in the right bushy operand", "[outer_yan][resimplify]") {
	auto root = SimplicityNode(0);
	AddSimplicityEdge(*root, SimplicityNode(1), JoinType::LEFT, 1, JoinType::LEFT);
	auto right = SimplicityNode(2);
	AddSimplicityEdge(*right, SimplicityNode(3), JoinType::RIGHT, 2, JoinType::RIGHT);
	AddSimplicityEdge(*root, std::move(right), JoinType::OUTER, 3, JoinType::LEFT);
	AddSimplicityEdge(*root, SimplicityNode(4), JoinType::OUTER, 4, JoinType::OUTER);
	OrderedJoinTree tree(std::move(root));
	REQUIRE(Resimplification::IsSimple(tree));
	Resimplification pass;
	pass.Apply(tree);
	REQUIRE(pass.reverts == 0);
	REQUIRE(tree.Root().children[1].kind == JoinType::OUTER);
	// Even though R2 is not a direct binary child of the restored join,
	// its NULL padding must be detected throughout that input subtree.
	tree.Root().children[1].kind = JoinType::LEFT;
	REQUIRE_FALSE(Resimplification::IsSimple(tree));
}

TEST_CASE("outer_yan resimplification: follows evaluation order across OJT depth", "[outer_yan][resimplify]") {
	auto root = SimplicityNode(0);
	auto middle = SimplicityNode(1);
	AddSimplicityEdge(*middle, SimplicityNode(2), JoinType::LEFT, 2, JoinType::LEFT);
	AddSimplicityEdge(*root, std::move(middle), JoinType::LEFT, 1, JoinType::LEFT);
	OrderedJoinTree tree(std::move(root));
	// (R0 LEFT R1) LEFT R2 is simple; changing the second join to INNER
	// rejects R1 padding, despite the OJT storing that edge below R1.
	REQUIRE(Resimplification::IsSimple(tree));
	tree.Root().children[0].child->children[0].kind = JoinType::INNER;
	REQUIRE_FALSE(Resimplification::IsSimple(tree));
}

TEST_CASE("outer_yan resimplification: rejects malformed or NULL-tolerant skeletons", "[outer_yan][resimplify]") {
	auto root = SimplicityNode(0);
	AddSimplicityEdge(*root, SimplicityNode(1), JoinType::LEFT, 1, JoinType::LEFT);
	AddSimplicityEdge(*root, SimplicityNode(2), JoinType::LEFT, 2, JoinType::LEFT);
	OrderedJoinTree tree(std::move(root));
	SECTION("uninitialized order") {
		tree.Root().children[0].order = 0;
	}
	SECTION("duplicate order") {
		tree.Root().children[1].order = 1;
	}
	SECTION("mismatched predicate endpoints") {
		tree.Root().children[0].info->cond_right_relation_id = 2;
	}
	SECTION("NULL-tolerant predicate") {
		auto &conditions = tree.Root().children[0].info->conditions;
		conditions.clear();
		conditions.emplace_back(
		    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER, ColumnBinding(TableIndex(0), ProjectionIndex(0))),
		    make_uniq<BoundColumnRefExpression>(LogicalType::INTEGER, ColumnBinding(TableIndex(1), ProjectionIndex(0))),
		    ExpressionType::COMPARE_NOT_DISTINCT_FROM);
	}
	REQUIRE_FALSE(Resimplification::IsSimple(tree));
}
