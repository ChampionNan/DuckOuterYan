-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: warehouse on-hand stock threshold
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=cs.cs_item_sk; group_key=inv.inv_item_sk
-- semantic_filter: tpcds_inventory_stock; tier=medium; warehouse on-hand stock threshold
-- predicate: inv.inv_quantity_on_hand <= 315
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT inv.inv_item_sk AS group_key, MIN(cs.cs_item_sk) AS min_key
FROM ((((catalog_sales cs INNER JOIN inventory inv ON cs.cs_item_sk = inv.inv_item_sk) LEFT OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk)
WHERE inv.inv_quantity_on_hand <= 315
GROUP BY inv.inv_item_sk;
