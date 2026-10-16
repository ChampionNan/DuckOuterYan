-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: catalog sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpcds_catalog_date; tier=medium; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-06-28' AND DATE '2000-11-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (catalog_returns cr INNER JOIN (warehouse w LEFT OUTER JOIN (item i RIGHT OUTER JOIN (catalog_sales cs FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number)
WHERE d.d_date BETWEEN DATE '1999-06-28' AND DATE '2000-11-23';
