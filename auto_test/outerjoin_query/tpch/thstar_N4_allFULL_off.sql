SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((lineitem FULL OUTER JOIN orders ON l_orderkey=o_orderkey) FULL OUTER JOIN part ON l_partkey=p_partkey) FULL OUTER JOIN supplier ON l_suppkey=s_suppkey);
