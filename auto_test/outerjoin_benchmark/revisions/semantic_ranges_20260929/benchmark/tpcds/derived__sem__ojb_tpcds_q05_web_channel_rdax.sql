-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (web_site web LEFT OUTER JOIN (web_returns wr FULL OUTER JOIN (web_sales ws INNER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) ON wr.wr_item_sk = ws.ws_item_sk) ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
