-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_web_date; tier=low; web sales reporting period
-- predicate: D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (customer_address CA FULL OUTER JOIN (customer_demographics CD INNER JOIN (customer C LEFT OUTER JOIN (item I RIGHT OUTER JOIN (web_sales WS FULL OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) ON WS.ws_item_sk = I.i_item_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk) ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_current_addr_sk = CA.ca_address_sk)
WHERE D.d_date BETWEEN DATE '2000-08-10' AND DATE '2000-09-19';
