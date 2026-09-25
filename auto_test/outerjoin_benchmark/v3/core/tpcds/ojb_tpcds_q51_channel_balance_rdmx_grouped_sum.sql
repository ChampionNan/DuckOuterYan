-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_sum; anchor=ws.ws_sold_date_sk; group_key=d.d_date_sk
SELECT d.d_date_sk AS group_key, SUM(ws.ws_sold_date_sk) AS key_sum
FROM (store_sales ss FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = ss.ss_item_sk)
WHERE ws.ws_order_number % 1000 = 0
GROUP BY d.d_date_sk;
