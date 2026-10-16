-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpcds_store_date; tier=medium; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((customer c FULL OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) INNER JOIN item i ON ss.ss_item_sk = i.i_item_sk) LEFT OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21';
