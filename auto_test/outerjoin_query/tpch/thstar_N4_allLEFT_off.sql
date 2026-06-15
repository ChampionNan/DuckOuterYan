SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((lineitem LEFT OUTER JOIN orders ON l_orderkey=o_orderkey) LEFT OUTER JOIN part ON l_partkey=p_partkey) LEFT OUTER JOIN supplier ON l_suppkey=s_suppkey);
