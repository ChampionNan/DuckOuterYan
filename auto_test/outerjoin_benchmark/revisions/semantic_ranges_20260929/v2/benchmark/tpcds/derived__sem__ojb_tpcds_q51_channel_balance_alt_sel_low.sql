-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((web_sales ws FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
