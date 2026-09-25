-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: Store sales retain optional return records and date, store, and item annotations.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT *
FROM ((((store_sales ss LEFT OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) FULL OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) INNER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE ss.ss_ticket_number % 1000 = 0;
