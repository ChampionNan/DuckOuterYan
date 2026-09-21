-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=ss.ss_customer_sk; predicate=hash(anchor) % 20 = 0
SELECT *
FROM (date_dim d FULL OUTER JOIN (web_sales ws FULL OUTER JOIN (item i FULL OUTER JOIN (store_sales ss FULL OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_item_sk = i.i_item_sk) ON i.i_item_sk = ws.ws_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 1000 = 0)
  AND hash(ss.ss_customer_sk) % 20 = 0;
