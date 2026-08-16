SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    RIGHT OUTER JOIN supplier ON n_nationkey = s_nationkey
    LEFT OUTER JOIN partsupp  ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part      ON ps_partkey = p_partkey
WHERE s_acctbal > 500;
