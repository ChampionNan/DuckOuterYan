-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_store_date; tier=medium; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk) LEFT OUTER JOIN store s ON ss.ss_store_sk = s.s_store_sk) RIGHT OUTER JOIN item i ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21';
