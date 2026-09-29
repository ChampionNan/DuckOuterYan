-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: TPC-H Q5 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_low; intended band 0–5% of the calibration population
-- semantic_filter: tpch_q05_period; tier=low; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (((nation n FULL OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) INNER JOIN customer c ON n.n_nationkey = c.c_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15';
