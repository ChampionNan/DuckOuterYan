SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((region INNER JOIN nation ON r_regionkey=n_regionkey) INNER JOIN supplier ON n_nationkey=s_nationkey);
