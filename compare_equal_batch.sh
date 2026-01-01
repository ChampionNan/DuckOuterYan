#!/bin/bash

# Helper function to run the comparison
compare_pair() {
    local file1=$1
    local file2=$2

    # Check if files exist
    if [ ! -f "$file1" ]; then
        echo "⚠️  MISSING: $file1"
        return
    fi
    if [ ! -f "$file2" ]; then
        echo "⚠️  MISSING: $file2"
        return
    fi

    # Run the script and capture output
    result=$(./compare_equal.sh "$file1" "$file2")

    if echo "$result" | grep -q "SUCCESS"; then
        echo "✅ PASS: $file1 <-> $file2"
    else
        echo "❌ FAIL: $file1 <-> $file2"
        echo "   (Run './compare_equal.sh $file1 $file2' to see differences)"
    fi
}

# Test suite functions
test_association1() {
    local BASE_DIR_1="outerjoin_test/association1"
    echo "---- Testing Association 1 Queries ----"
    compare_pair "$BASE_DIR_1/q11_1.sql" "$BASE_DIR_1/q11_2.sql"
    compare_pair "$BASE_DIR_1/q12_1.sql" "$BASE_DIR_1/q12_1_r.sql"
    compare_pair "$BASE_DIR_1/q12_2.sql" "$BASE_DIR_1/q12_2_r.sql"
    compare_pair "$BASE_DIR_1/q12_1.sql" "$BASE_DIR_1/q12_2.sql"
    compare_pair "$BASE_DIR_1/q22_1.sql" "$BASE_DIR_1/q22_1_r.sql"
    compare_pair "$BASE_DIR_1/q22_2.sql" "$BASE_DIR_1/q22_2_r.sql"
    compare_pair "$BASE_DIR_1/q22_1.sql" "$BASE_DIR_1/q22_2.sql"
    compare_pair "$BASE_DIR_1/q31_1.sql" "$BASE_DIR_1/q31_1_r.sql"
    compare_pair "$BASE_DIR_1/q31_2.sql" "$BASE_DIR_1/q31_2_r.sql"
    compare_pair "$BASE_DIR_1/q31_1.sql" "$BASE_DIR_1/q31_2.sql"
    compare_pair "$BASE_DIR_1/q32_1.sql" "$BASE_DIR_1/q32_1_r.sql"
    compare_pair "$BASE_DIR_1/q32_2.sql" "$BASE_DIR_1/q32_2_r.sql"
    compare_pair "$BASE_DIR_1/q32_1.sql" "$BASE_DIR_1/q32_2.sql"
    compare_pair "$BASE_DIR_1/q33_1.sql" "$BASE_DIR_1/q33_1_r.sql"
    compare_pair "$BASE_DIR_1/q33_2.sql" "$BASE_DIR_1/q33_2_r.sql"
    compare_pair "$BASE_DIR_1/q33_1.sql" "$BASE_DIR_1/q33_2.sql"
    compare_pair "$BASE_DIR_1/q34_1.sql" "$BASE_DIR_1/q34_1_r.sql"
    compare_pair "$BASE_DIR_1/q34_2.sql" "$BASE_DIR_1/q34_2_r.sql"
    compare_pair "$BASE_DIR_1/q34_1.sql" "$BASE_DIR_1/q34_2.sql"
    compare_pair "$BASE_DIR_1/q42_1.sql" "$BASE_DIR_1/q42_1_r.sql"
    compare_pair "$BASE_DIR_1/q42_2.sql" "$BASE_DIR_1/q42_2_r.sql"
    compare_pair "$BASE_DIR_1/q42_1.sql" "$BASE_DIR_1/q42_2.sql"
    compare_pair "$BASE_DIR_1/q44_1.sql" "$BASE_DIR_1/q44_2.sql"
}

test_association2() {
    local BASE_DIR_2="outerjoin_test/association2"
    echo "---- Testing Association 2 Queries ----"
    compare_pair "$BASE_DIR_2/q13_21.sql" "$BASE_DIR_2/q13_22.sql"
    compare_pair "$BASE_DIR_2/q13_31.sql" "$BASE_DIR_2/q13_32.sql"
    compare_pair "$BASE_DIR_2/q13_1.sql" "$BASE_DIR_2/q13_21.sql"
    compare_pair "$BASE_DIR_2/q13_1.sql" "$BASE_DIR_2/q13_31.sql"
    compare_pair "$BASE_DIR_2/q14_21.sql" "$BASE_DIR_2/q14_22.sql"
    compare_pair "$BASE_DIR_2/q14_1.sql" "$BASE_DIR_2/q14_21.sql"
    compare_pair "$BASE_DIR_2/q21_1.sql" "$BASE_DIR_2/q21_2.sql"
    compare_pair "$BASE_DIR_2/q23_1.sql" "$BASE_DIR_2/q23_2.sql"
    compare_pair "$BASE_DIR_2/q24_21.sql" "$BASE_DIR_2/q24_22.sql"
    compare_pair "$BASE_DIR_2/q24_1.sql" "$BASE_DIR_2/q24_21.sql"
    compare_pair "$BASE_DIR_2/q41_1.sql" "$BASE_DIR_2/q41_2.sql"
    compare_pair "$BASE_DIR_2/q43_1.sql" "$BASE_DIR_2/q43_2.sql"
}

test_simplification() {
    local BASE_DIR_3="outerjoin_test/simplification"
    echo "---- Testing Simplification Queries ----"
    compare_pair "$BASE_DIR_3/q1.sql" "$BASE_DIR_3/q1_r.sql"
    compare_pair "$BASE_DIR_3/q2.sql" "$BASE_DIR_3/q2_r.sql"
}

test_desimplification() {
    local BASE_DIR_4="outerjoin_test/desimplification"
    echo "---- Testing Desimplification Queries ----"
    compare_pair "$BASE_DIR_4/q1.sql" "$BASE_DIR_4/q1_r.sql"
    compare_pair "$BASE_DIR_4/q2.sql" "$BASE_DIR_4/q2_r.sql"
    compare_pair "$BASE_DIR_4/q3.sql" "$BASE_DIR_4/q3_r.sql"
}

test_aggregation() {
    local BASE_DIR_5="outerjoin_test/aggregation"
    echo "---- Testing Aggregation Queries ----"
    compare_pair "$BASE_DIR_5/q1.sql" "$BASE_DIR_5/q1_r.sql"
    compare_pair "$BASE_DIR_5/q1.sql" "$BASE_DIR_5/q1_2.sql"
    compare_pair "$BASE_DIR_5/q2.sql" "$BASE_DIR_5/q2_r.sql"
    compare_pair "$BASE_DIR_5/q2.sql" "$BASE_DIR_5/q2_2.sql"
    compare_pair "$BASE_DIR_5/q3.sql" "$BASE_DIR_5/q3_r.sql"
    compare_pair "$BASE_DIR_5/q3.sql" "$BASE_DIR_5/q3_2.sql"
    compare_pair "$BASE_DIR_5/q4.sql" "$BASE_DIR_5/q4_r.sql"
    compare_pair "$BASE_DIR_5/q4.sql" "$BASE_DIR_5/q4_2.sql"
    compare_pair "$BASE_DIR_5/q5.sql" "$BASE_DIR_5/q5_r.sql"
    compare_pair "$BASE_DIR_5/q5.sql" "$BASE_DIR_5/q5_2.sql"
}

# Parse command line argument
TEST_NUM=${1:-all}

echo "========================================"
echo "Running Manual Comparison Suite"
echo "========================================"

case $TEST_NUM in
    1)
        test_association1
        ;;
    2)
        test_association2
        ;;
    3)
        test_simplification
        ;;
    4)
        test_desimplification
        ;;
    5)
        test_aggregation
        ;;
    all)
        test_association1
        test_association2
        test_simplification
        test_desimplification
        ;;
    *)
        echo "Usage: $0 [1|2|3|4|all]"
        echo "  1 - Test Association 1"
        echo "  2 - Test Association 2"
        echo "  3 - Test Simplification"
        echo "  4 - Test Desimplification"
        echo "  all (default) - Run all tests"
        exit 1
        ;;
esac

echo "========================================"
echo "Test Suite Complete"
echo "========================================"