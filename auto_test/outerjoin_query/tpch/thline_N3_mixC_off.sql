SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((region RIGHT OUTER JOIN nation ON r_regionkey=n_regionkey) FULL OUTER JOIN supplier ON n_nationkey=s_nationkey);
