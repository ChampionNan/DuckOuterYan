SELECT * FROM (((lineitem RIGHT OUTER JOIN orders ON l_orderkey=o_orderkey) RIGHT OUTER JOIN part ON l_partkey=p_partkey) RIGHT OUTER JOIN supplier ON l_suppkey=s_suppkey);
