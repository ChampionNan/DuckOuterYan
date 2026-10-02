-- query_type: join; family: tpcds
-- source: TPC-DS Q51
-- semantic_filter: tpcds_web_date; tier=high; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (store_sales ss LEFT OUTER JOIN (web_sales ws INNER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = ss.ss_item_sk)
WHERE d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
