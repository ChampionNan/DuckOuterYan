-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_current_addr_sk, ca.ca_address_sk, c.c_customer_sk, ws.ws_bill_customer_sk, ws.ws_item_sk, i.i_item_sk, ws.ws_sold_date_sk, d.d_date_sk, ws.ws_ship_mode_sk, sm.sm_ship_mode_sk
FROM ((((item i INNER JOIN web_sales ws ON ws.ws_item_sk = i.i_item_sk) FULL OUTER JOIN ship_mode sm ON ws.ws_ship_mode_sk = sm.sm_ship_mode_sk) RIGHT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN (customer c FULL OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ws.ws_bill_customer_sk)
WHERE d.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
