SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE s_suppkey >= 10;
