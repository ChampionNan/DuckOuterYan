-- query_type: aggregate; family: tpcds
-- source: TPC-DS Q72
-- semantic_filter: tpcds_inventory_stock; tier=medium; warehouse on-hand stock threshold
-- predicate: inv.inv_quantity_on_hand <= 315
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT inv.inv_item_sk AS group_key, MAX(cs.cs_item_sk) AS max_key
FROM (promotion p INNER JOIN (item i FULL OUTER JOIN (warehouse w RIGHT OUTER JOIN (inventory inv LEFT OUTER JOIN catalog_sales cs ON cs.cs_item_sk = inv.inv_item_sk) ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_promo_sk = p.p_promo_sk)
WHERE inv.inv_quantity_on_hand <= 315
GROUP BY inv.inv_item_sk;
