SELECT *
FROM partsupp
    FULL OUTER JOIN part ON ps_partkey = p_partkey
    LEFT OUTER JOIN supplier ON ps_suppkey = s_suppkey
    RIGHT OUTER JOIN lineitem ON ps_partkey = l_partkey
WHERE l_orderkey % 7 <> 0;
