SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((customer INNER JOIN orders ON c_custkey=o_custkey) INNER JOIN ((region INNER JOIN nation ON r_regionkey=n_regionkey) INNER JOIN supplier ON n_nationkey=s_nationkey) ON c_nationkey=n_nationkey);
