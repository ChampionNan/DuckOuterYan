-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_sqlstorm_tpcds_10809_ldmx
-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=archive_projection
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM ((((customer c RIGHT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) FULL OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE (c.c_customer_sk % 100) < 30;
