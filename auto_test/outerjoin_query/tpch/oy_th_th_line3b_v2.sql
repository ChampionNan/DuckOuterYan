SELECT *
FROM customer
    FULL OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE ps_availqty BETWEEN 1 AND 100;
