-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (store_returns sr FULL OUTER JOIN (date_dim d INNER JOIN (store s LEFT OUTER JOIN (store_sales ss RIGHT OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
