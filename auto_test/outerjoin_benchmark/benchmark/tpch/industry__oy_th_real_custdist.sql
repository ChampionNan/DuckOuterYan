SELECT *
FROM customer
    FULL OUTER JOIN orders   ON c_custkey = o_custkey
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE c_acctbal > 0;
