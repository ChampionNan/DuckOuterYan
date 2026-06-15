SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((orders LEFT OUTER JOIN lineitem ON o_orderkey=l_orderkey) LEFT OUTER JOIN (part LEFT OUTER JOIN partsupp ON p_partkey=ps_partkey) ON l_partkey=p_partkey);
