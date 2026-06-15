SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((orders INNER JOIN lineitem ON o_orderkey=l_orderkey) INNER JOIN (part INNER JOIN partsupp ON p_partkey=ps_partkey) ON l_partkey=p_partkey);
