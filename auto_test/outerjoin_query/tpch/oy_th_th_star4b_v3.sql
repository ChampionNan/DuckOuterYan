SELECT *
FROM partsupp
    LEFT OUTER JOIN part ON ps_partkey = p_partkey
    INNER JOIN supplier ON ps_suppkey = s_suppkey
    RIGHT OUTER JOIN lineitem ON ps_partkey = l_partkey
WHERE l_extendedprice BETWEEN 1 AND 100;
