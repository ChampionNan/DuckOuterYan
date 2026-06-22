SELECT c_mktsegment, SUM(o_totalprice) AS total_val
FROM customer
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE l_quantity > 0 AND l_quantity < 10000
GROUP BY c_mktsegment;
