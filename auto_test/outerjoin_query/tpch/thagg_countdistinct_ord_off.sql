SET disabled_optimizers TO 'outer_yan';
SELECT c_mktsegment, COUNT(DISTINCT o_orderkey) AS n_orders FROM ((customer RIGHT OUTER JOIN orders ON c_custkey=o_custkey) RIGHT OUTER JOIN lineitem ON o_orderkey=l_orderkey) GROUP BY c_mktsegment;
