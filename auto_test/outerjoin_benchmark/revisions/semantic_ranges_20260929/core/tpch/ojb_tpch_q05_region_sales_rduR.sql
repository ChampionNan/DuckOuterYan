-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: TPC-H Q5 order reporting period
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpch_q05_period; tier=low; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (region r INNER JOIN (nation n LEFT OUTER JOIN (customer c RIGHT OUTER JOIN (orders o FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey) ON n.n_nationkey = c.c_nationkey) ON r.r_regionkey = n.n_regionkey)
WHERE o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1994-03-15';
