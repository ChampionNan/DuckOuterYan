-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_web_date; tier=high; web sales reporting period
-- predicate: D.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((item I LEFT OUTER JOIN web_sales WS ON WS.ws_item_sk = I.i_item_sk) RIGHT OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk) INNER JOIN ((customer_address CA RIGHT OUTER JOIN customer C ON C.c_current_addr_sk = CA.ca_address_sk) FULL OUTER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) ON C.c_customer_sk = WS.ws_bill_customer_sk)
WHERE D.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
