SELECT s_nationkey, COUNT(*) AS cnt_val
FROM nation
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
WHERE ps_availqty % 7 <> 0
GROUP BY s_nationkey;
