SELECT *
FROM region
    LEFT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_availqty < 50000;
