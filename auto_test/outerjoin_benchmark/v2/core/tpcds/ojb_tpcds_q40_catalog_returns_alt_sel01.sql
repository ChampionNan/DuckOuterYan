-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; alternate mixed form; bushy grouping is structurally ineligible
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_version: v2
-- selectivity_sweep: sel01; approximately 1% of the v1 anchor domain; anchor=cs.cs_order_number; predicate=hash(anchor) % 100 = 0
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM ((((catalog_sales cs FULL OUTER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number) RIGHT OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) INNER JOIN item i ON cs.cs_item_sk = i.i_item_sk) LEFT OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE (cs.cs_order_number % 1000 = 0)
  AND hash(cs.cs_order_number) % 100 = 0;
