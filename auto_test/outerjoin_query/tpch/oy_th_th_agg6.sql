SELECT s_nationkey, MIN(ps_supplycost) AS lo_val
FROM nation
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_availqty > 500
GROUP BY s_nationkey;
