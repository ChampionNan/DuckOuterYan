-- source: SQLStorm v1.0/tpcds/queries/11376.sql
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: store sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_store_date; tier=high; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((web_sales ws INNER JOIN item i ON i.i_item_sk = ws.ws_item_sk) FULL OUTER JOIN ((store_sales ss RIGHT OUTER JOIN customer c ON c.c_customer_sk = ss.ss_customer_sk) LEFT OUTER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-04-06' AND DATE '2002-01-24';
