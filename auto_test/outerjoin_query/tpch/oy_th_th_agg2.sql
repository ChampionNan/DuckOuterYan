SELECT n_name, SUM(l_quantity) AS total_qty, AVG(l_extendedprice) AS avg_price
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    INNER JOIN customer ON n_nationkey = c_nationkey
    FULL OUTER JOIN orders ON c_custkey = o_custkey
WHERE l_linenumber >= 10
GROUP BY n_name;
