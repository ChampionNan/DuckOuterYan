SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((customer FULL OUTER JOIN orders ON c_custkey=o_custkey) RIGHT OUTER JOIN ((region INNER JOIN nation ON r_regionkey=n_regionkey) LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey) ON c_nationkey=n_nationkey);
