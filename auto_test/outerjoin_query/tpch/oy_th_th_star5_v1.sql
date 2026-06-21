SELECT *
FROM lineitem
    RIGHT OUTER JOIN orders ON l_orderkey = o_orderkey
    FULL OUTER JOIN part ON l_partkey = p_partkey
    LEFT OUTER JOIN supplier ON l_suppkey = s_suppkey
    RIGHT OUTER JOIN nation ON s_nationkey = n_nationkey
WHERE l_discount IN (2, 4, 6, 8, 10, 12, 14);
