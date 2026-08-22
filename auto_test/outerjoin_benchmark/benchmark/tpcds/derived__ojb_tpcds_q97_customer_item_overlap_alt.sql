-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; deterministic alternate mixed labeling; bushy grouping is structurally ineligible
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
SELECT *
FROM ((store_sales ss LEFT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) FULL OUTER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk AND ss.ss_item_sk = cs.cs_item_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
