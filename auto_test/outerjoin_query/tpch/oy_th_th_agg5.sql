SELECT c_mktsegment, SUM(o_totalprice) AS total_val
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE c_acctbal > 0 AND c_acctbal < 10000
GROUP BY c_mktsegment;
