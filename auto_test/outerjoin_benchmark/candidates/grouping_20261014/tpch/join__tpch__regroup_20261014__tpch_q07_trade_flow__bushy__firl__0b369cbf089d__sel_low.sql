-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__tpch__tpch_q07_trade_flow__bushy__flir__01a4a016__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT s.s_suppkey, l.l_suppkey, l.l_orderkey, o.o_orderkey, o.o_custkey, c.c_custkey, s.s_nationkey, n.n_nationkey
FROM (((orders o FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) RIGHT OUTER JOIN (supplier s LEFT OUTER JOIN nation n ON s.s_nationkey = n.n_nationkey) ON s.s_suppkey = l.l_suppkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15';
