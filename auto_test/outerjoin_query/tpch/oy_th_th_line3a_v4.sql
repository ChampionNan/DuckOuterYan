SELECT *
FROM region
    FULL OUTER JOIN nation ON r_regionkey = n_regionkey
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
WHERE p_retailprice > 0 AND p_retailprice < 10000;
