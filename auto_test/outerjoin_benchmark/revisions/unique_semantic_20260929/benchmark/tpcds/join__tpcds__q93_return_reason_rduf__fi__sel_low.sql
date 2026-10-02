-- query_type: join; family: tpcds
-- source: TPC-DS Q93
-- semantic_filter: tpcds_return_reason; tier=low; TPC-DS Q93 return-reason categories
-- predicate: r.r_reason_desc = 'reason 28'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (store_sales ss FULL OUTER JOIN (store_returns sr INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk) ON ss.ss_item_sk = sr.sr_item_sk)
WHERE r.r_reason_desc = 'reason 28';
