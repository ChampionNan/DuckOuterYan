SELECT p_size, COUNT(*) AS cnt, AVG(l_discount) AS avg_disc
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN customer ON n_nationkey = c_nationkey
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
WHERE p_size IN (2, 4, 6, 8, 10, 12, 14)
GROUP BY p_size;
