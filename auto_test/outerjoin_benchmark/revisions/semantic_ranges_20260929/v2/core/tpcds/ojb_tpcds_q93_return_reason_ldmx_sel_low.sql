-- source: TPC-DS Q93
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: TPC-DS Q93 return-reason categories
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpcds_return_reason; tier=low; TPC-DS Q93 return-reason categories
-- predicate: r.r_reason_desc = 'reason 28'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((store_sales ss FULL OUTER JOIN store_returns sr ON ss.ss_item_sk = sr.sr_item_sk) INNER JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk)
WHERE r.r_reason_desc = 'reason 28';
