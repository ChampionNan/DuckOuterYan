-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: warehouse on-hand stock threshold
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_inventory_stock; tier=medium; warehouse on-hand stock threshold
-- predicate: inv.inv_quantity_on_hand <= 315
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM (warehouse w LEFT OUTER JOIN (inventory inv INNER JOIN (item i RIGHT OUTER JOIN (catalog_sales cs FULL OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_item_sk = inv.inv_item_sk) ON inv.inv_warehouse_sk = w.w_warehouse_sk)
WHERE inv.inv_quantity_on_hand <= 315;
