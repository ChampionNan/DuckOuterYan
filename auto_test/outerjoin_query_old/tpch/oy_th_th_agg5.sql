SELECT s_nationkey, SUM(ps_supplycost) AS total_val
FROM nation
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_availqty BETWEEN 1 AND 100
GROUP BY s_nationkey;
