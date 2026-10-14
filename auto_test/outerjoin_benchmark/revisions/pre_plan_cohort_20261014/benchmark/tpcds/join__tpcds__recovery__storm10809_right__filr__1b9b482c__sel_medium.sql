-- corpus_revision: balanced-screened-20261002; component: tpcds-recovery-20261005
-- historical_pattern: derived__ojb_sqlstorm_tpcds_10809_rdmx_sel001
-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- selectivity: medium; frozen base-entity calibration, not joined output
-- policy: performance-conditioned historical recovery; pending cpu9 measurement
-- transformation: archived mixed join expression and filter relation; three WHERE cohorts; projection=archive_projection
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM (time_dim t RIGHT OUTER JOIN (date_dim d LEFT OUTER JOIN (store_sales ss INNER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE (c.c_customer_sk % 100) < 30;
