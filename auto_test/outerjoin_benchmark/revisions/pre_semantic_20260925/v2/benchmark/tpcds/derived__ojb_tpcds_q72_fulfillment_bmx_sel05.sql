-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_version: v2
-- selectivity_sweep: sel05; approximately 5% of the v1 anchor domain; anchor=cs.cs_item_sk; predicate=hash(anchor) % 20 = 0
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (((catalog_sales cs LEFT OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) INNER JOIN item i ON cs.cs_item_sk = i.i_item_sk) RIGHT OUTER JOIN (inventory inv FULL OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = inv.inv_item_sk)
WHERE (cs.cs_order_number % 1000 = 0)
  AND hash(cs.cs_item_sk) % 20 = 0;
