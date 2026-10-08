-- corpus_revision: balanced-screened-20261002; component: tpcds-selectivity-extension-20261008-r2
-- source_connected_subgraph: storm14368_branch5_bushy
-- source: SQLStorm v1.0/tpcds/queries/14368.sql
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: source-derived single-fact candidate; pending cpu9 measurement
-- transformation: connected subgraph of source equality edges; mixed join kinds/grouping; three WHERE cohorts; projection=select_star_source_subgraph
SELECT *
FROM (customer_address ca RIGHT OUTER JOIN customer c
        ON c.c_current_addr_sk = ca.ca_address_sk)
    FULL OUTER JOIN
    ((web_sales ws INNER JOIN item i ON ws.ws_item_sk = i.i_item_sk)
        LEFT OUTER JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk)
    ON c.c_customer_sk = ws.ws_bill_customer_sk
WHERE (c.c_customer_sk % 100) < 30;
