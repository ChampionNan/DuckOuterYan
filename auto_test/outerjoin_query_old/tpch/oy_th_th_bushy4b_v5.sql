SELECT *
FROM (( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) INNER JOIN ( supplier LEFT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE s_acctbal BETWEEN 1 AND 100;
