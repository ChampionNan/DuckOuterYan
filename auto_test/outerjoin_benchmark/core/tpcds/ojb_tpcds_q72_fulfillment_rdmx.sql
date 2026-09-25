-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (promotion p INNER JOIN (item i FULL OUTER JOIN (warehouse w RIGHT OUTER JOIN (inventory inv LEFT OUTER JOIN catalog_sales cs ON cs.cs_item_sk = inv.inv_item_sk) ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_promo_sk = p.p_promo_sk)
WHERE cs.cs_order_number % 1000 = 0;
