-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_current_addr_sk, ca.ca_address_sk, c.c_customer_sk, ws.ws_bill_customer_sk, ws.ws_item_sk, i.i_item_sk, ws.ws_sold_date_sk, d.d_date_sk, ws.ws_ship_mode_sk, sm.sm_ship_mode_sk
FROM (((((customer c FULL OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) INNER JOIN web_sales ws ON c.c_customer_sk = ws.ws_bill_customer_sk) RIGHT OUTER JOIN item i ON ws.ws_item_sk = i.i_item_sk) LEFT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk)
WHERE d.d_date BETWEEN DATE '1999-11-18' AND DATE '2001-06-12';
