SELECT r_name, COUNT(*) AS cnt, MAX(c_acctbal) AS max_bal
FROM customer
    RIGHT OUTER JOIN orders ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE s_acctbal % 3 = 0
GROUP BY r_name;
