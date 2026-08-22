SELECT c_custkey, c_name, count(l_orderkey) AS line_cnt
FROM customer
    LEFT OUTER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE c_acctbal > 0
GROUP BY c_custkey, c_name;
