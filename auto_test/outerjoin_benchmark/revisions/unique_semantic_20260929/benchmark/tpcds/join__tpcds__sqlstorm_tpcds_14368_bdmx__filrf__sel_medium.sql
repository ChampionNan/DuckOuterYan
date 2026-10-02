-- query_type: join; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- semantic_filter: tpcds_web_date; tier=medium; web sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((item i LEFT OUTER JOIN web_sales ws ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) INNER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk)
WHERE d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
