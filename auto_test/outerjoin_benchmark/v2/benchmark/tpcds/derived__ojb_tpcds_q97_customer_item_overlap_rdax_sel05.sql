-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ss.ss_sold_date_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (catalog_sales cs FULL OUTER JOIN (store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(ss.ss_sold_date_sk) % 20 = 0;
