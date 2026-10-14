-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpch__th_real_supplier_right__fil__sel_low
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    INNER JOIN partsupp  ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part      ON ps_partkey = p_partkey
WHERE partsupp.ps_supplycost <= 31.21;