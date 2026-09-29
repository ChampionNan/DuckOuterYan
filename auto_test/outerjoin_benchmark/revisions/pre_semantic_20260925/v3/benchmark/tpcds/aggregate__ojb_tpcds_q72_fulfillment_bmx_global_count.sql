-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: global_count; anchor=cs.cs_item_sk; group_key=inv.inv_item_sk
SELECT COUNT(*) AS row_count
FROM (((catalog_sales cs LEFT OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk) INNER JOIN item i ON cs.cs_item_sk = i.i_item_sk) RIGHT OUTER JOIN (inventory inv FULL OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk) ON cs.cs_item_sk = inv.inv_item_sk)
WHERE cs.cs_order_number % 1000 = 0;
