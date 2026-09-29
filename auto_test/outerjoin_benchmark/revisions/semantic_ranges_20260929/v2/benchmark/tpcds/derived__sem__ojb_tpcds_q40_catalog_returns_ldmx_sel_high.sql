-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: catalog sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_catalog_date; tier=high; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '1998-10-13' AND DATE '2001-08-08'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM ((((catalog_sales cs INNER JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number) LEFT OUTER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) RIGHT OUTER JOIN item i ON cs.cs_item_sk = i.i_item_sk) FULL OUTER JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '1998-10-13' AND DATE '2001-08-08';
