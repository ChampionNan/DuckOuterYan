-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; cross-product-free bushy grouping with mixed join labeling
-- business_semantics: Customer shopping-context coverage adapted from SQLStorm: customer address, sale date, and sale time are modeled as optional context.
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM ((customer c LEFT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk AND ca.ca_state = 'CA') INNER JOIN ((store_sales ss RIGHT OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk) FULL OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk AND d.d_year = 2023) ON c.c_customer_sk = ss.ss_customer_sk)
WHERE (c.c_customer_sk % 1000 = 0 OR c.c_customer_sk IS NULL);
