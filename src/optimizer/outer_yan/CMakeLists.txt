add_library_unity(
  duckdb_optimizer_outer_yan
  OBJECT
  # semi-join build/probe filter carriers and insertion
  semi_join/hash_filter.cpp
  semi_join/key_bitmap.cpp
  semi_join/semi_join_filter.cpp
  semi_join/semijoin_insertion.cpp
  # common IR data structures and applicability gate
  common/applicability.cpp
  common/operator_tree.cpp
  common/ordered_join_tree.cpp
  common/outer_yan_trace.cpp
  common/outer_yan_tree.cpp
  # main OuterYan algorithm pipeline phases
  pipeline/agg_pushdown.cpp
  pipeline/aggregate_pushdown_outer.cpp
  pipeline/desimplification.cpp
  pipeline/outer_yan_dp.cpp
  pipeline/outer_yan_optimizer.cpp
  pipeline/outer_yan_post.cpp
  pipeline/outer_yan_pre.cpp
  pipeline/resimplification.cpp
  pipeline/simplification.cpp)
set(ALL_OBJECT_FILES
    ${ALL_OBJECT_FILES} $<TARGET_OBJECTS:duckdb_optimizer_outer_yan>
    PARENT_SCOPE)
