-- query_type: aggregate; family: tpcds
-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT c.c_current_addr_sk AS group_key, SUM(ss.ss_customer_sk) AS key_sum
FROM ((((customer c RIGHT OUTER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) FULL OUTER JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN time_dim t ON ss.ss_sold_time_sk = t.t_time_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
GROUP BY c.c_current_addr_sk;
