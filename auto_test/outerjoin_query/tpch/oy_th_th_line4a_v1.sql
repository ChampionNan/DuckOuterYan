SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE o_totalprice % 2 = 1;
