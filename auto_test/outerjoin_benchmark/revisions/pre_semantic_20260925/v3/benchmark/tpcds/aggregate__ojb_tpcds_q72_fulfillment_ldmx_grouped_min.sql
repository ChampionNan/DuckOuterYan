-- source: TPC-DS Q72
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: Catalog fulfillment coverage: sales are matched with inventory, warehouse, item, and optional promotion information.
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=cs.cs_item_sk; group_key=inv.inv_item_sk
SELECT inv.inv_item_sk AS group_key, MIN(cs.cs_item_sk) AS min_key
FROM ((((catalog_sales cs INNER JOIN inventory inv ON cs.cs_item_sk = inv.inv_item_sk) LEFT OUTER JOIN warehouse w ON inv.inv_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk)
WHERE cs.cs_order_number % 1000 = 0
GROUP BY inv.inv_item_sk;
