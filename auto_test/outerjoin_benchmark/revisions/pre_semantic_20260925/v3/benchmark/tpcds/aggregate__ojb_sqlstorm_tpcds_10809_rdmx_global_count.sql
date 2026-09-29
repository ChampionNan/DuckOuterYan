-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Customer shopping-context coverage adapted from SQLStorm: customer address, sale date, and sale time are modeled as optional context.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ss.ss_customer_sk; group_key=c.c_current_addr_sk
SELECT COUNT(*) AS row_count
FROM (time_dim t RIGHT OUTER JOIN (date_dim d LEFT OUTER JOIN (store_sales ss INNER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE c.c_customer_sk % 1000 = 0;
