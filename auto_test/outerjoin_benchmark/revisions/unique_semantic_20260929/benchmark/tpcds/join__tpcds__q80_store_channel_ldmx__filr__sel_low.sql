-- query_type: join; family: tpcds
-- source: TPC-DS Q80
-- semantic_filter: tpcds_store_date; tier=low; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) RIGHT OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-09' AND DATE '2000-09-20';
