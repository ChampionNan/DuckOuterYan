SELECT * FROM (((lineitem INNER JOIN orders ON l_orderkey=o_orderkey) INNER JOIN part ON l_partkey=p_partkey) INNER JOIN supplier ON l_suppkey=s_suppkey);
