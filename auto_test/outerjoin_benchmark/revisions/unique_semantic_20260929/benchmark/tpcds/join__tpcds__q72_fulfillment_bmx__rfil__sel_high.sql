-- query_type: join; family: tpcds
-- source: TPC-DS Q72
-- semantic_filter: tpcds_inventory_stock; tier=high; warehouse on-hand stock threshold
-- predicate: inv.inv_quantity_on_hand <= 579
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (((catalog_sales cs LEFT OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) INNER JOIN item i ON cs.cs_item_sk = i.i_item_sk) RIGHT OUTER JOIN (inventory inv FULL OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = inv.inv_item_sk)
WHERE inv.inv_quantity_on_hand <= 579;
