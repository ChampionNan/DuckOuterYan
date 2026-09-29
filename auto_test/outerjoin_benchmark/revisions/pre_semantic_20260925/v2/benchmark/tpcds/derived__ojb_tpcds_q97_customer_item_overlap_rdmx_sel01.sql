-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=ss.ss_sold_date_sk; predicate=hash(anchor) % 100 = 0
SELECT *
FROM (catalog_sales cs LEFT OUTER JOIN (date_dim d INNER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE (ss.ss_ticket_number % 1000 = 0)
  AND hash(ss.ss_sold_date_sk) % 100 = 0;
