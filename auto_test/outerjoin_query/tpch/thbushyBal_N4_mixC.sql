SELECT * FROM ((orders RIGHT OUTER JOIN lineitem ON o_orderkey=l_orderkey) FULL OUTER JOIN (part LEFT OUTER JOIN partsupp ON p_partkey=ps_partkey) ON l_partkey=p_partkey);
