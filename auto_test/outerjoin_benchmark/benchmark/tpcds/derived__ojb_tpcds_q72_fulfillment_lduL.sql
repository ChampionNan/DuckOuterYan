-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; secondary left-deep FULL-outer control
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM ((((promotion p FULL OUTER JOIN catalog_sales cs ON cs.cs_promo_sk = p.p_promo_sk) FULL OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN inventory inv ON cs.cs_item_sk = inv.inv_item_sk) FULL OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk)
WHERE cs.cs_order_number % 1000 = 0;
