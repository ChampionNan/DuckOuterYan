-- source: TPC-DS Q40
-- transformation: connected join-subgraph adaptation; balanced mixed secondary right-deep source-derived form
-- business_semantics: catalog sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_catalog_date; tier=low; catalog sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT cs.cs_order_number, cs.cs_item_sk, cr.cr_return_quantity, w.w_state, i.i_item_id, d.d_date
FROM (date_dim d RIGHT OUTER JOIN (item i LEFT OUTER JOIN (catalog_returns cr FULL OUTER JOIN (catalog_sales cs INNER JOIN warehouse w ON cs.cs_warehouse_sk = w.w_warehouse_sk) ON cs.cs_order_number = cr.cr_order_number) ON cs.cs_item_sk = i.i_item_sk) ON cs.cs_sold_date_sk = d.d_date_sk)
WHERE d.d_date BETWEEN DATE '2000-01-25' AND DATE '2000-04-26';
