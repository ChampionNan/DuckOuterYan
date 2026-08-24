-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
SELECT *
FROM ((catalog_sales cs FULL OUTER JOIN store_sales ss ON ss.ss_customer_sk = cs.cs_bill_customer_sk) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
