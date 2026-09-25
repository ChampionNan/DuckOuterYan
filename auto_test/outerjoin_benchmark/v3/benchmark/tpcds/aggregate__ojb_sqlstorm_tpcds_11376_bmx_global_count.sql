-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ss.ss_customer_sk; group_key=c.c_customer_sk
SELECT COUNT(*) AS row_count
FROM ((customer c LEFT OUTER JOIN (store_sales ss INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON c.c_customer_sk = ss.ss_customer_sk) RIGHT OUTER JOIN (item i FULL OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE c.c_customer_sk % 1000 = 0;
