SELECT *
FROM partsupp
    RIGHT OUTER JOIN part ON ps_partkey = p_partkey
    FULL OUTER JOIN supplier ON ps_suppkey = s_suppkey
    LEFT OUTER JOIN lineitem ON ps_partkey = l_partkey
WHERE ps_availqty IN (1, 5, 10, 50, 100, 500);
