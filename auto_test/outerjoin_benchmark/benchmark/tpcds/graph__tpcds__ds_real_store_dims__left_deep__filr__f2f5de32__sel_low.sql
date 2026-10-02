-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpcds__ds_real_store_dims__filr__sel_medium
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss_item_sk, ss_sales_price, i_brand, c_first_name, s_store_name
FROM store_sales
    FULL OUTER JOIN item      ON ss_item_sk = i_item_sk
    INNER JOIN customer  ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN store     ON ss_store_sk = s_store_sk
    RIGHT OUTER JOIN promotion ON ss_promo_sk = p_promo_sk
WHERE store_sales.ss_quantity <= 3;