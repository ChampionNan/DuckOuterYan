-- source: SQLStorm v1.0/tpcds/queries/28643.sql
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: web sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_web_date; tier=high; web sales reporting period
-- predicate: D.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((((customer C FULL OUTER JOIN customer_address CA ON C.c_current_addr_sk = CA.ca_address_sk) INNER JOIN customer_demographics CD ON C.c_current_cdemo_sk = CD.cd_demo_sk) LEFT OUTER JOIN web_sales WS ON C.c_customer_sk = WS.ws_bill_customer_sk) RIGHT OUTER JOIN item I ON WS.ws_item_sk = I.i_item_sk) FULL OUTER JOIN date_dim D ON WS.ws_sold_date_sk = D.d_date_sk)
WHERE D.d_date BETWEEN DATE '1999-05-08' AND DATE '2001-12-23';
