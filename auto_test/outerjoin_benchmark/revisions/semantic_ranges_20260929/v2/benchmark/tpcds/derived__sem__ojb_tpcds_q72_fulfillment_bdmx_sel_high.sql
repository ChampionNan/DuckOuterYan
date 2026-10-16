-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: warehouse on-hand stock threshold
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_inventory_stock; tier=high; warehouse on-hand stock threshold
-- predicate: inv.inv_quantity_on_hand <= 579
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, inv.inv_quantity_on_hand, w.w_warehouse_name, i.i_item_id, p.p_promo_name
FROM ((warehouse w INNER JOIN inventory inv ON inv.inv_warehouse_sk = w.w_warehouse_sk) FULL OUTER JOIN ((item i LEFT OUTER JOIN catalog_sales cs ON cs.cs_item_sk = i.i_item_sk) RIGHT OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) ON cs.cs_item_sk = inv.inv_item_sk)
WHERE inv.inv_quantity_on_hand <= 579;
