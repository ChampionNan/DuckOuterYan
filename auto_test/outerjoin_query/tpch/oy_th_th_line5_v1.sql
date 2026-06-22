SELECT *
FROM region
    RIGHT OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN customer ON n_nationkey = c_nationkey
    LEFT OUTER JOIN orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
WHERE r_regionkey % 7 <> 0;
