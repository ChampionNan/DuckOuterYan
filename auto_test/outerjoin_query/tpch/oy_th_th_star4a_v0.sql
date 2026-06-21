SELECT *
FROM lineitem
    LEFT OUTER JOIN orders ON l_orderkey = o_orderkey
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE c_custkey >= 100 AND c_custkey <= 9000;
