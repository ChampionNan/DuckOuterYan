-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer applicability form
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=cs.cs_order_number; predicate=hash(anchor) % 1000 = 0
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (date_dim d FULL OUTER JOIN (item i FULL OUTER JOIN (catalog_returns cr FULL OUTER JOIN (catalog_sales cs FULL OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE (cs.cs_order_number % 1000 = 0)
  AND hash(cs.cs_order_number) % 1000 = 0;
