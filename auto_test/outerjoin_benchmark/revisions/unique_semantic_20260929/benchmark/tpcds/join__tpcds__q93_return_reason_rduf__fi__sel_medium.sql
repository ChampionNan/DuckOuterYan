-- query_type: join; family: tpcds
-- source: TPC-DS Q93
-- semantic_filter: tpcds_return_reason; tier=medium; TPC-DS Q93 return-reason categories
-- predicate: (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have')
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (store_sales ss FULL OUTER JOIN (store_returns sr INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE (r.r_reason_desc = 'reason 28' OR r.r_reason_desc = 'Did not fit' OR r.r_reason_desc = 'Wrong size' OR r.r_reason_desc = 'Did not like the color' OR r.r_reason_desc = 'Did not like the make' OR r.r_reason_desc = 'Did not like the model' OR r.r_reason_desc = 'Not the product that was ordred' OR r.r_reason_desc = 'Does not work with a product that I have');
