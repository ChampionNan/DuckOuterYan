SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
WHERE r_regionkey > 0 AND r_regionkey < 10000;
