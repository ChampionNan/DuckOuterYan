-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/tpcds/queries/10809.sql
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c.c_current_addr_sk AS group_key, MAX(ss.ss_customer_sk) AS max_key
FROM ((customer c INNER JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk) RIGHT OUTER JOIN (time_dim t LEFT OUTER JOIN (date_dim d FULL OUTER JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_sold_time_sk = t.t_time_sk) ON c.c_customer_sk = ss.ss_customer_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
GROUP BY c.c_current_addr_sk;
