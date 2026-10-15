-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpch__sqlstorm_tpch_25509__bushy__rifrl__4e202a33__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey
FROM (((orders o RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) LEFT OUTER JOIN (part p RIGHT OUTER JOIN (supplier s FULL OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1993-06-01' AND DATE '1996-12-31';
