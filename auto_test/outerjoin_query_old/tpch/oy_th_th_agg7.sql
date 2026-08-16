SELECT s_nationkey, MAX(ps_supplycost) AS hi_val
FROM nation
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_availqty >= 100 AND ps_availqty <= 9000
GROUP BY s_nationkey;
