-- source: TPC-DS Q5
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpcds_web_date; tier=medium; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((web_returns wr RIGHT OUTER JOIN web_sales ws ON wr.wr_item_sk = ws.ws_item_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
