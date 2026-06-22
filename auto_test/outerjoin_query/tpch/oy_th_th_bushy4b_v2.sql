SELECT *
FROM (( region FULL OUTER JOIN nation ON r_regionkey = n_regionkey) LEFT OUTER JOIN ( supplier RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey) ON n_nationkey = s_nationkey)
WHERE ps_availqty % 7 <> 0;
