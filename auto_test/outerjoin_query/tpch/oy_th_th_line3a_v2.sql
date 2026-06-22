SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
WHERE r_regionkey BETWEEN 50 AND 5000;
