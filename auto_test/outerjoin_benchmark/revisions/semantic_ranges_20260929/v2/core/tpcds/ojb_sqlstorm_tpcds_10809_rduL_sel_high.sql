-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM (customer_address ca RIGHT OUTER JOIN (customer c FULL OUTER JOIN (date_dim d INNER JOIN (store_sales ss LEFT OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON c.c_customer_sk = ss.ss_customer_sk) ON c.c_current_addr_sk = ca.ca_address_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
