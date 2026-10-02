-- query_type: aggregate; family: tpcds
-- source: TPC-DS Q51
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM ((web_sales ws LEFT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN store_sales ss ON ws.ws_item_sk = ss.ss_item_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
