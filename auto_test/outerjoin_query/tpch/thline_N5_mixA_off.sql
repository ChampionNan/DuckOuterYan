SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((((region LEFT OUTER JOIN nation ON r_regionkey=n_regionkey) INNER JOIN customer ON n_nationkey=c_nationkey) RIGHT OUTER JOIN orders ON c_custkey=o_custkey) FULL OUTER JOIN lineitem ON o_orderkey=l_orderkey);
