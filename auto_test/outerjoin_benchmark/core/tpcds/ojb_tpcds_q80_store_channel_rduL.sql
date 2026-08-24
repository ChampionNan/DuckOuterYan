-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
SELECT *
FROM (store_returns sr FULL OUTER JOIN (date_dim d FULL OUTER JOIN (store s FULL OUTER JOIN (store_sales ss FULL OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
