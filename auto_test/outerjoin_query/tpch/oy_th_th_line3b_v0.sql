SELECT *
FROM customer
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE c_acctbal IN (1, 5, 10, 50, 100, 500);
