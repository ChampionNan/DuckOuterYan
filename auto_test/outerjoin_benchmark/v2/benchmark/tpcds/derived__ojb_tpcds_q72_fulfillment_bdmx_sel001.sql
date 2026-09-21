-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=cs.cs_item_sk; predicate=hash(anchor) % 1000 = 0
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM ((warehouse w FULL OUTER JOIN inventory inv ON inv.inv_warehouse_sk = w.w_warehouse_sk) FULL OUTER JOIN ((item i FULL OUTER JOIN catalog_sales cs ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) ON cs.cs_item_sk = inv.inv_item_sk)
WHERE (cs.cs_order_number % 1000 = 0)
  AND hash(cs.cs_item_sk) % 1000 = 0;
