SELECT *
FROM (( lineitem RIGHT OUTER JOIN part ON l_partkey = p_partkey) INNER JOIN (( nation FULL OUTER JOIN region ON n_regionkey = r_regionkey) LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON l_suppkey = s_suppkey)
WHERE l_discount < 50000;
