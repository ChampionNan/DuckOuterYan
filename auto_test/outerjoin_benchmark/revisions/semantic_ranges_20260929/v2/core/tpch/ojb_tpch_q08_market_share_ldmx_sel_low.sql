-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: TPC-H Q8 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpch_q08_period; tier=low; TPC-H Q8 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((((part p FULL OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) INNER JOIN orders o ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) RIGHT OUTER JOIN nation n ON c.c_nationkey = n.n_nationkey) FULL OUTER JOIN region r ON n.n_regionkey = r.r_regionkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
