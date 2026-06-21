SELECT *
FROM region RIGHT OUTER JOIN (nation INNER JOIN (supplier FULL OUTER JOIN (partsupp LEFT OUTER JOIN (part RIGHT OUTER JOIN lineitem ON p_partkey = l_partkey) ON ps_partkey = p_partkey) ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey) ON r_regionkey = n_regionkey
WHERE s_acctbal % 2 = 1;
