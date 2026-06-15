SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((orders FULL OUTER JOIN lineitem ON o_orderkey=l_orderkey) FULL OUTER JOIN (part FULL OUTER JOIN partsupp ON p_partkey=ps_partkey) ON l_partkey=p_partkey);
