-- query_type: join; family: tpcds
-- source: TPC-DS Q97
-- semantic_filter: tpcds_store_date; tier=medium; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (date_dim d FULL OUTER JOIN (store_sales ss INNER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21';
