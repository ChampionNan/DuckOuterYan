SELECT n_regionkey, SUM(s_acctbal) AS tot_bal, COUNT(*) AS n_supp
FROM lineitem
    RIGHT OUTER JOIN part ON l_partkey = p_partkey
    FULL OUTER JOIN supplier ON l_suppkey = s_suppkey
WHERE ps_availqty % 2 = 1
GROUP BY n_regionkey;
