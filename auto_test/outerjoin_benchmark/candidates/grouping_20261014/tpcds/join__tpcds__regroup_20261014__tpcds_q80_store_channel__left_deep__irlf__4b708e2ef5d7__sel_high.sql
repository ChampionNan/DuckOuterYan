-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpcds__tpcds_q80_store_channel__left_deep__ifrl__30fc53d1__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT ss.ss_item_sk, sr.sr_item_sk, ss.ss_ticket_number, sr.sr_ticket_number, ss.ss_sold_date_sk, d.d_date_sk, ss.ss_store_sk, s.s_store_sk, i.i_item_sk
FROM ((((store_sales ss INNER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number) RIGHT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) FULL OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
