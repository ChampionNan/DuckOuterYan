-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: TPC-H Q8 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpch_q08_period; tier=low; TPC-H Q8 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (orders o INNER JOIN ((nation n LEFT OUTER JOIN customer c ON c.c_nationkey = n.n_nationkey) RIGHT OUTER JOIN region r ON n.n_regionkey = r.r_regionkey) ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
