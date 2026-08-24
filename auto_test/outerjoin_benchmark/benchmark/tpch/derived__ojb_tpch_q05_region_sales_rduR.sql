-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; secondary right-deep FULL-outer control
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (region r FULL OUTER JOIN (nation n FULL OUTER JOIN (customer c FULL OUTER JOIN (orders o FULL OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey) ON n.n_nationkey = c.c_nationkey) ON r.r_regionkey = n.n_regionkey)
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
