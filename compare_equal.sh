#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status

FILE1=$1
FILE2=$2
DB_FILE=${3:-rstk_db}

# Check if database file exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file '$DB_FILE' does not exist"
    exit 1
fi

# Check if query files exist
if [ ! -f "$FILE1" ]; then
    echo "Error: Query file '$FILE1' does not exist"
    exit 1
fi

if [ ! -f "$FILE2" ]; then
    echo "Error: Query file '$FILE2' does not exist"
    exit 1
fi

echo "Comparing queries from $FILE1 and $FILE2 using database $DB_FILE..."

duckdb_bin="/duckdb/build/release/duckdb"  # Adjust this if duckdb is not in your PATH

# Execute query1 and save result to CSV
$duckdb_bin "$DB_FILE" -csv -header < "$FILE1" > q1_temp.csv

# Execute query2 and save result to CSV
$duckdb_bin "$DB_FILE" -csv -header < "$FILE2" > q2_temp.csv

# Compare the two result sets
COMPARE_QUERY="
CREATE TABLE t1 AS SELECT * FROM read_csv('q1_temp.csv', auto_detect=true, header=true, all_varchar=true);
CREATE TABLE t2 AS SELECT * FROM read_csv('q2_temp.csv', auto_detect=true, header=true, all_varchar=true);

SELECT 'In $FILE1 but not $FILE2' as source, * FROM (SELECT * FROM t1 EXCEPT SELECT * FROM t2)
UNION ALL
SELECT 'In $FILE2 but not $FILE1' as source, * FROM (SELECT * FROM t2 EXCEPT SELECT * FROM t1);
"

# Run the comparison in a temporary database
OUTPUT=$($duckdb_bin -noheader -list -c "$COMPARE_QUERY")

# Cleanup temporary files
rm q1_temp.csv q2_temp.csv

if [ -z "$OUTPUT" ]; then
    echo "✅ SUCCESS: Results are identical."
    exit 0
else
    echo "❌ FAILURE: Results differ."
    echo "Differences:"
    echo "$OUTPUT"
    exit 1
fi