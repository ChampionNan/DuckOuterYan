-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpcds__sqlstorm_tpcds_10809__bushy__filr__b775d306__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM ((customer c LEFT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) INNER JOIN (time_dim t FULL OUTER JOIN (date_dim d RIGHT OUTER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_sold_time_sk = t.t_time_sk) ON c.c_customer_sk = ss.ss_customer_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
