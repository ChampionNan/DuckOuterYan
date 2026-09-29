-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpcds_web_date; tier=medium; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (date_dim d LEFT OUTER JOIN (web_sales ws RIGHT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
