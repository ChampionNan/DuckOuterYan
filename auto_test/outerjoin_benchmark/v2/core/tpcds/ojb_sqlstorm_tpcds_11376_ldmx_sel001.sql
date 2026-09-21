-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; primary left-deep FULL-outer applicability form
-- business_semantics: A SQLStorm tpcds query pattern whose source relation graph is retained; the anchor sample is enriched under controlled preservation semantics.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ss.ss_customer_sk; predicate=hash(anchor) % 1000 = 0
SELECT *
FROM ((((customer c FULL OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) FULL OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk) FULL OUTER JOIN web_sales ws ON i.i_item_sk = ws.ws_item_sk) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk)
WHERE (c.c_customer_sk % 1000 = 0)
  AND hash(ss.ss_customer_sk) % 1000 = 0;
