-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
-- corpus_revision: v1-mixed-20260922
SELECT *
FROM ((store_sales ss FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) INNER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
