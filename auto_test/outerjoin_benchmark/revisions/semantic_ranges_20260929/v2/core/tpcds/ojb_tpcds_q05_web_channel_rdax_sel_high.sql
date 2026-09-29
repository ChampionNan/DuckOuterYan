-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_web_date; tier=high; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (web_site web LEFT OUTER JOIN (web_returns wr FULL OUTER JOIN (web_sales ws INNER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) ON wr.wr_item_sk = ws.ws_item_sk) ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
