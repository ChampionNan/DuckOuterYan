-- query_type: join; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (customer_address ca INNER JOIN (customer c LEFT OUTER JOIN (item i RIGHT OUTER JOIN (date_dim d FULL OUTER JOIN (web_sales ws INNER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = i.i_item_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk) ON c.c_current_addr_sk = ca.ca_address_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
