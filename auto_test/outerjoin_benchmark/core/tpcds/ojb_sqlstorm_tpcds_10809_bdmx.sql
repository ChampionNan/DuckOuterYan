-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; secondary cross-product-free bushy FULL-outer applicability form
-- business_semantics: Customer shopping-context coverage adapted from SQLStorm: customer address, sale date, and sale time are modeled as optional context.
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM (((date_dim d FULL OUTER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) FULL OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk) FULL OUTER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ss.ss_customer_sk)
WHERE c.c_customer_sk % 1000 = 0;
