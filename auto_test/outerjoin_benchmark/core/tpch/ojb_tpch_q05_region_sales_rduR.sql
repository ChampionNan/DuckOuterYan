-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; uniform right-deep RIGHT OUTER JOIN control
-- business_semantics: Regional sales coverage: retain the selected region hierarchy and represent missing customers, orders, or line items by NULLs.
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (lineitem l RIGHT OUTER JOIN (orders o RIGHT OUTER JOIN (customer c RIGHT OUTER JOIN (nation n RIGHT OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) ON n.n_nationkey = c.c_nationkey) ON c.c_custkey = o.o_custkey AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01') ON o.o_orderkey = l.l_orderkey)
WHERE (r.r_name = 'ASIA' OR r.r_regionkey IS NULL);
