-- source: TPC-DS Q80
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: store sales reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpcds_store_date; tier=medium; store sales reporting period
-- predicate: d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (item i FULL OUTER JOIN (store s RIGHT OUTER JOIN (date_dim d LEFT OUTER JOIN (store_returns sr INNER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk) ON ss.ss_sold_date_sk = d.d_date_sk) ON ss.ss_store_sk = s.s_store_sk) ON ss.ss_item_sk = i.i_item_sk)
WHERE d.d_date BETWEEN DATE '1999-11-09' AND DATE '2001-06-21';
