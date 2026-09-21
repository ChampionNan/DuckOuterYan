-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; right-deep FULL-outer applicability form
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
-- corpus_version: v2
-- selectivity_sweep: sel001; approximately 0.1% of the v1 anchor domain; anchor=o.o_custkey; predicate=hash(anchor) % 1000 = 0
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (lineitem l FULL OUTER JOIN (orders o FULL OUTER JOIN (customer c FULL OUTER JOIN (nation n FULL OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE (r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01')
  AND hash(o.o_custkey) % 1000 = 0;
