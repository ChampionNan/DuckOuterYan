SELECT *
FROM (( lineitem FULL OUTER JOIN part ON l_partkey = p_partkey) INNER JOIN (( nation LEFT OUTER JOIN region ON n_regionkey = r_regionkey) INNER JOIN supplier ON n_nationkey = s_nationkey) ON l_suppkey = s_suppkey)
WHERE s_acctbal <= 1000;
