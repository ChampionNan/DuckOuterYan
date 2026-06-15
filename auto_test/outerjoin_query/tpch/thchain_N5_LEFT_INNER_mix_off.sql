SET disabled_optimizers TO 'outer_yan';
SELECT * FROM customer LEFT OUTER JOIN orders ON c_custkey=o_custkey INNER JOIN lineitem ON o_orderkey=l_orderkey LEFT OUTER JOIN supplier ON l_suppkey=s_suppkey INNER JOIN nation ON s_nationkey=n_nationkey;
