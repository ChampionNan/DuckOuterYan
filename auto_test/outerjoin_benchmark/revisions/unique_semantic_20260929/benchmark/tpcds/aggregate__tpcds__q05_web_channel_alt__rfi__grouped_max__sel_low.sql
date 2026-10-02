-- query_type: aggregate; family: tpcds
-- source: TPC-DS Q5
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT wr.wr_item_sk AS group_key, MAX(ws.ws_item_sk) AS max_key
FROM (((web_returns wr RIGHT OUTER JOIN web_sales ws ON wr.wr_item_sk = ws.ws_item_sk) FULL OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
GROUP BY wr.wr_item_sk;
