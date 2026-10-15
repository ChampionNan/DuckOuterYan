-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpch__sqlstorm_tpch_17751__right_deep__lir__ebcf8b47__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT p.p_partkey, ps.ps_partkey, ps.ps_suppkey, s.s_suppkey, l.l_partkey
FROM (lineitem l LEFT OUTER JOIN (part p RIGHT OUTER JOIN (supplier s INNER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey) ON p.p_partkey = l.l_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-03-15';
