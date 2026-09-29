-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: TPC-DS Q93 return-reason categories
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: tpcds_return_reason; tier=medium; TPC-DS Q93 return-reason categories
-- predicate: (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have')
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (reason r LEFT OUTER JOIN (store_returns sr INNER JOIN store_sales ss ON ss.ss_item_sk = sr.sr_item_sk) ON sr.sr_reason_sk = r.r_reason_sk)
WHERE (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have');
