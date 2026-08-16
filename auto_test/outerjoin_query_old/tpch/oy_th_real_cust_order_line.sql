SELECT c_custkey, c_name, n_name, o_orderdate, l_quantity, l_extendedprice
FROM customer
    LEFT OUTER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN nation   ON c_nationkey = n_nationkey
    LEFT OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE c_acctbal > 1000;
