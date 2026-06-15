SET disabled_optimizers TO 'outer_yan';
SELECT * FROM nation LEFT OUTER JOIN supplier ON n_nationkey=s_nationkey LEFT OUTER JOIN lineitem ON s_suppkey=l_suppkey;
