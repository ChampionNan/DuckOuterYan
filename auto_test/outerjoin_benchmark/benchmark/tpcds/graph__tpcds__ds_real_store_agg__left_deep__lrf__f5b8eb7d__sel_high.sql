-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpcds__ds_real_store_agg__lrf__sel_high
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT *
FROM store_sales
    LEFT OUTER JOIN item     ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store    ON ss_store_sk = s_store_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
WHERE store_sales.ss_quantity <= 58;