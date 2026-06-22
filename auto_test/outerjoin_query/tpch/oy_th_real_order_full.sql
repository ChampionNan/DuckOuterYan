SELECT o_orderkey, o_orderstatus, l_linestatus, p_brand, ps_availqty
FROM orders
    FULL OUTER JOIN lineitem ON o_orderkey = l_orderkey
    LEFT OUTER JOIN part     ON l_partkey = p_partkey
    LEFT OUTER JOIN partsupp ON l_partkey = ps_partkey AND l_suppkey = ps_suppkey
WHERE o_totalprice > 50000;
