-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpcds_store_date; tier=low; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (catalog_sales cs LEFT OUTER JOIN (date_dim d INNER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20';
