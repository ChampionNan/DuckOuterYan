SELECT *
FROM partsupp
    LEFT OUTER JOIN part ON ps_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON ps_suppkey = s_suppkey
    FULL OUTER JOIN lineitem ON ps_partkey = l_partkey
WHERE l_extendedprice % 3 = 0;
