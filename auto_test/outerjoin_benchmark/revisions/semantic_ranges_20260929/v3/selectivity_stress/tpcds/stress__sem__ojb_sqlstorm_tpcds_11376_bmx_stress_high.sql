-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v3
-- derived_from_corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress_high; 40–80% of the calibration population
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((customer c LEFT OUTER JOIN (store_sales ss INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON c.c_customer_sk = ss.ss_customer_sk) RIGHT OUTER JOIN (item i FULL OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
