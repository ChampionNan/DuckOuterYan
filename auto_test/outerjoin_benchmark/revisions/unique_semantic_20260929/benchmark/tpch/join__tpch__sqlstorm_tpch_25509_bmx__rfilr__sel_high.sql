-- query_type: join; family: tpch
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- semantic_filter: sqlstorm_order_period; tier=high; SQLStorm 25509 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((part p RIGHT OUTER JOIN (partsupp ps FULL OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey) INNER JOIN (lineitem l LEFT OUTER JOIN (orders o RIGHT OUTER JOIN customer c ON o.o_custkey = c.c_custkey) ON l.l_orderkey = o.o_orderkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
