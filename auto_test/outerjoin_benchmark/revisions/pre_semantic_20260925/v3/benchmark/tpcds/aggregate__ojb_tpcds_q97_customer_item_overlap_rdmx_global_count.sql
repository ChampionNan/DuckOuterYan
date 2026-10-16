-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=ss.ss_sold_date_sk; group_key=d.d_date_sk
SELECT COUNT(*) AS row_count
FROM (catalog_sales cs LEFT OUTER JOIN (date_dim d INNER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
