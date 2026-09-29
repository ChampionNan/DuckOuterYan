-- query_type: join; family: tpcds
-- source: TPC-DS Q80
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (item i LEFT OUTER JOIN (store s INNER JOIN (store_returns sr RIGHT OUTER JOIN (store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
