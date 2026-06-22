SELECT s_nationkey, COUNT(*) AS cnt, MIN(ps_supplycost) AS min_cost
FROM nation
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_supplycost BETWEEN 50 AND 5000
GROUP BY s_nationkey;
