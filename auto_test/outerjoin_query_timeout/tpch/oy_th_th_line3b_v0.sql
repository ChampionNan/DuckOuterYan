SELECT *
FROM customer
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE c_acctbal < 50000;
