-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ws.ws_sold_date_sk; group_key=d.d_date_sk
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT d.d_date_sk AS group_key, SUM(ws.ws_sold_date_sk) AS key_sum
FROM (store_sales ss FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = ss.ss_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
GROUP BY d.d_date_sk;
