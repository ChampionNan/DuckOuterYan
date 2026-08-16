-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; uniform right-deep LEFT OUTER JOIN control
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
SELECT *
FROM (item i LEFT OUTER JOIN (store s LEFT OUTER JOIN (date_dim d LEFT OUTER JOIN (store_returns sr LEFT OUTER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL);
