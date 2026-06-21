SELECT *
FROM partsupp
    RIGHT OUTER JOIN part ON ps_partkey = p_partkey
    INNER JOIN supplier ON ps_suppkey = s_suppkey
    FULL OUTER JOIN lineitem ON ps_partkey = l_partkey
WHERE l_linenumber > 500;
