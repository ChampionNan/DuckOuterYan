SELECT *
FROM (( lineitem LEFT OUTER JOIN part ON l_partkey = p_partkey) RIGHT OUTER JOIN (( nation FULL OUTER JOIN region ON n_regionkey = r_regionkey) LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey) ON l_suppkey = s_suppkey)
WHERE p_retailprice > 0 AND p_retailprice < 10000;
