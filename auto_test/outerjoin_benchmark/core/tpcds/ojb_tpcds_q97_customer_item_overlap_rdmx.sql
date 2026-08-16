-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Store and catalog activity is reconciled for the same customer-item pair.
SELECT *
FROM (catalog_sales cs RIGHT OUTER JOIN (date_dim d INNER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_customer_sk = cs.cs_bill_customer_sk AND ss.ss_item_sk = cs.cs_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL);
