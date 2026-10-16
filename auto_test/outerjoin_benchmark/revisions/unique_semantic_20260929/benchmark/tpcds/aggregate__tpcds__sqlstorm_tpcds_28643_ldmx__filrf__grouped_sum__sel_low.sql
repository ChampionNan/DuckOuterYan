-- query_type: aggregate; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT C.c_current_addr_sk AS group_key, SUM(WS.ws_bill_customer_sk) AS key_sum
FROM (((((customer C FULL OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) INNER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) LEFT OUTER JOIN web_sales WS ON C.c_customer_sk = WS.ws_bill_customer_sk) RIGHT OUTER JOIN item I ON WS.ws_item_sk = I.i_item_sk) FULL OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk)
WHERE D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
GROUP BY C.c_current_addr_sk;
