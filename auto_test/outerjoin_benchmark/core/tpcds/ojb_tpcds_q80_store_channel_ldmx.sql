-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; primary left-deep mixed join labeling
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
SELECT *
FROM ((((store_sales ss LEFT OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) INNER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE (ss.ss_ticket_number % 1000 = 0 OR ss.ss_ticket_number IS NULL);
