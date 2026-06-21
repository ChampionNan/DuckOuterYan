SELECT s_nationkey, COUNT(*) AS cnt, MIN(ps_supplycost) AS min_cost
FROM lineitem
    LEFT OUTER JOIN part ON l_partkey = p_partkey
    RIGHT OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE n_nationkey BETWEEN 50 AND 5000
GROUP BY s_nationkey;
