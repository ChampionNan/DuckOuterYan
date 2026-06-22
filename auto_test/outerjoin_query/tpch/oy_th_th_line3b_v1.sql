SELECT *
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE l_discount % 7 <> 0;
