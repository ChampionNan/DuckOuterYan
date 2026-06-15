SELECT c_mktsegment, SUM(l_extendedprice) AS revenue FROM ((customer FULL OUTER JOIN orders ON c_custkey=o_custkey) FULL OUTER JOIN lineitem ON o_orderkey=l_orderkey) GROUP BY c_mktsegment;
