add_library_unity(test_optimizer_outer_yan OBJECT
                  semi_join_filter_test.cpp
                  key_bitmap_test.cpp
                  hash_filter_test.cpp
                  applicability_test.cpp
                  passes_integration_test.cpp
                  partial_reduction_test.cpp
                  resimplification_test.cpp
                  semijoin_insertion_schedule_test.cpp
                  postgres_plan_replay_test.cpp
                  sj_operator_bench.cpp)

set(UNITTEST_OBJECT_FILES
    ${UNITTEST_OBJECT_FILES} $<TARGET_OBJECTS:test_optimizer_outer_yan>
    PARENT_SCOPE)
