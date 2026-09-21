-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Customer shopping-context coverage adapted from SQLStorm: customer address, sale date, and sale time are modeled as optional context.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=ss.ss_customer_sk; predicate=hash(anchor) % 1000 = 0
SELECT c.c_customer_id, ca.ca_city, ss.ss_ticket_number, ss.ss_quantity, d.d_date, t.t_hour
FROM (time_dim t FULL OUTER JOIN (date_dim d FULL OUTER JOIN (store_sales ss FULL OUTER JOIN (customer_address ca FULL OUTER JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk) ON c.c_customer_sk = ss.ss_customer_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE (c.c_customer_sk % 1000 = 0)
  AND hash(ss.ss_customer_sk) % 1000 = 0;
