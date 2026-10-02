-- query_type: join; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- semantic_filter: tpcds_web_date; tier=high; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (ship_mode sm LEFT OUTER JOIN (date_dim d INNER JOIN (item i FULL OUTER JOIN (web_sales ws RIGHT OUTER JOIN (customer_address ca LEFT OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk) ON ws.ws_item_sk = i.i_item_sk) ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk)
WHERE d.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
