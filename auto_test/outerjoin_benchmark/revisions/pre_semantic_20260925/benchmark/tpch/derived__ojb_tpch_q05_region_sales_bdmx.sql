-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced mixed secondary connected bushy source-derived form
-- business_semantics: Regional sales in the source date window: retain region-filtered coverage while exposing missing line-item information.
-- corpus_revision: v1-mixed-graph25-20260925
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM (((nation n FULL OUTER JOIN region r ON r.r_regionkey = n.n_regionkey) INNER JOIN customer c ON n.n_nationkey = c.c_nationkey) LEFT OUTER JOIN (lineitem l RIGHT OUTER JOIN orders o ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= DATE '1994-01-01' AND o.o_orderdate < DATE '1995-01-01';
