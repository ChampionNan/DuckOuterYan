SELECT o_orderpriority, COUNT(*) AS cnt
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE l_extendedprice > 100
GROUP BY o_orderpriority;
