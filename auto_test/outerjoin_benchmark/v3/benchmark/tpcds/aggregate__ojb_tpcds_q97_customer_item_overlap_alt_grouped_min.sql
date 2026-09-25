-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=ss.ss_sold_date_sk; group_key=d.d_date_sk
SELECT d.d_date_sk AS group_key, MIN(ss.ss_sold_date_sk) AS min_key
FROM ((store_sales ss LEFT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE ss.ss_ticket_number % 1000 = 0
GROUP BY d.d_date_sk;
