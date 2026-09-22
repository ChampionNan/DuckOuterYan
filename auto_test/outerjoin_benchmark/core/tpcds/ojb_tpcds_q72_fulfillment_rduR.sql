-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_revision: v1-mixed-20260922
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (warehouse w LEFT OUTER JOIN (inventory inv INNER JOIN (item i RIGHT OUTER JOIN (catalog_sales cs FULL OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_item_sk = inv.inv_item_sk) ON inv.inv_warehouse_sk = w.w_warehouse_sk)
WHERE cs.cs_order_number % 1000 = 0;
