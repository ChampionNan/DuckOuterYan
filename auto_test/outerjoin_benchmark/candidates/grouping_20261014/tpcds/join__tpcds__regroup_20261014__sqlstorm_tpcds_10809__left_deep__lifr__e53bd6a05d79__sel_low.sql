-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpcds__recovery__storm10809_left__rfil__878e6f0a__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM ((((customer c LEFT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) INNER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE (c.c_customer_sk % 100) < 3;
