-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; semantics-equivalent right-deep mirror of the primary mixed labeling
-- business_semantics: Regional sales in the source date window: retain NULL-aware region coverage while exposing missing line-item information.
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (lineitem l RIGHT OUTER JOIN (orders o RIGHT OUTER JOIN (customer c RIGHT OUTER JOIN (nation n INNER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE (r.r_name = 'ASIA' OR r.r_regionkey IS NULL) AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
