SELECT *
FROM (( lineitem FULL OUTER JOIN part ON l_partkey = p_partkey) LEFT OUTER JOIN (( nation RIGHT OUTER JOIN region ON n_regionkey = r_regionkey) FULL OUTER JOIN supplier ON n_nationkey = s_nationkey) ON l_suppkey = s_suppkey)
WHERE l_extendedprice % 2 = 1;
