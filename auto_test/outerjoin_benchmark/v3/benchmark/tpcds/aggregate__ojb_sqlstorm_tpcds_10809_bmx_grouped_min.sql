-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Customer shopping-context coverage adapted from SQLStorm: customer address, sale date, and sale time are modeled as optional context.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=ss.ss_customer_sk; group_key=c.c_current_addr_sk
SELECT c.c_current_addr_sk AS group_key, MIN(ss.ss_customer_sk) AS min_key
FROM ((customer c INNER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) LEFT OUTER JOIN ((store_sales ss FULL OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON c.c_customer_sk = ss.ss_customer_sk)
WHERE c.c_customer_sk % 1000 = 0
GROUP BY c.c_current_addr_sk;
