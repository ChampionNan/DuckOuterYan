SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((region LEFT OUTER JOIN nation ON r_regionkey=n_regionkey) LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey);
