-- source: TPC-DS Q97
-- transformation: connected join-subgraph adaptation; balanced mixed alternate form; bushy grouping is structurally ineligible
-- business_semantics: store sales reporting period
-- corpus_version: v3
-- workload_role: source-derived aggregation coverage; no timing-based selection
-- aggregate_variant: grouped_min; anchor=ss.ss_sold_date_sk; group_key=d.d_date_sk
-- semantic_filter: tpcds_store_date; tier=medium; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT d.d_date_sk AS group_key, MIN(ss.ss_sold_date_sk) AS min_key
FROM ((store_sales ss LEFT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) RIGHT OUTER JOIN catalog_sales cs ON ss.ss_customer_sk = cs.cs_bill_customer_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
GROUP BY d.d_date_sk;
