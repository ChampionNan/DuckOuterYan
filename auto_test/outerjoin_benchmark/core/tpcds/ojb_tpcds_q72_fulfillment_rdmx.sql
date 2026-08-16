-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (promotion p RIGHT OUTER JOIN (item i INNER JOIN (warehouse w INNER JOIN (inventory inv INNER JOIN catalog_sales cs ON cs.cs_item_sk = inv.inv_item_sk AND cs.cs_quantity > inv.inv_quantity_on_hand) ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_promo_sk = p.p_promo_sk)
WHERE (cs.cs_order_number % 1000 = 0 OR cs.cs_order_number IS NULL);
