-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-DS Q97
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ss.ss_sold_date_sk, d.d_date_sk, ss.ss_customer_sk, cs.cs_bill_customer_sk, ss.ss_item_sk, cs.cs_item_sk
FROM ((date_dim d FULL OUTER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) INNER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk AND ss.ss_item_sk = cs.cs_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20';
