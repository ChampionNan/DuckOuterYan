SET disabled_optimizers TO 'outer_yan';
SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey;
