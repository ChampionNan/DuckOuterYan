-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_max; anchor=ss.ss_customer_sk; group_key=c.c_customer_sk
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT c.c_customer_sk AS group_key, MAX(ss.ss_customer_sk) AS max_key
FROM (date_dim d FULL OUTER JOIN (web_sales ws RIGHT OUTER JOIN (item i LEFT OUTER JOIN (store_sales ss INNER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_item_sk = i.i_item_sk) ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
GROUP BY c.c_customer_sk;
