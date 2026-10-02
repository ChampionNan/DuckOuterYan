-- query_type: aggregate; family: tpcds
-- source: TPC-DS Q5
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT COUNT(*) AS row_count
FROM (web_site web FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN (web_sales ws LEFT OUTER JOIN web_returns wr ON wr.wr_item_sk = ws.ws_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
