SELECT s_name, n_name, r_name, p_name, ps_availqty
FROM supplier
    FULL OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part     ON ps_partkey = p_partkey
    FULL OUTER JOIN nation   ON s_nationkey = n_nationkey
    FULL OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE s_acctbal > 1000;
