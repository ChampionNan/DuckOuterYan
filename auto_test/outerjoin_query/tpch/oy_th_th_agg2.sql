SELECT n_name, SUM(l_quantity) AS total_qty, AVG(l_extendedprice) AS avg_price
FROM nation
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN lineitem ON s_suppkey = l_suppkey
WHERE l_orderkey >= 10
GROUP BY n_name;
