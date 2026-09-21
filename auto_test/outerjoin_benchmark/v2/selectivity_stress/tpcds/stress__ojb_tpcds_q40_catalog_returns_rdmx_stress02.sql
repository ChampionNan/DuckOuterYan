-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Catalog return attribution: every qualifying catalog sale remains visible even when no matching return exists; dimensions enrich it.
-- corpus_version: v2
-- workload_role: metadata-selected balanced selectivity ablation
-- selectivity_stress: stress02; approximately 0.2% of hash buckets; anchor=cs.cs_order_number; predicate=hash(cs.cs_order_number) % 4000 < 8
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (date_dim d FULL OUTER JOIN (item i FULL OUTER JOIN (warehouse w FULL OUTER JOIN (catalog_returns cr FULL OUTER JOIN catalog_sales cs ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE hash(cs.cs_order_number) % 4000 < 8;
