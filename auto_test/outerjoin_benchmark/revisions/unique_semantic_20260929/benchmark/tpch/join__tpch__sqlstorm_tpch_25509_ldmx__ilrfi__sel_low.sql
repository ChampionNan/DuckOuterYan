-- query_type: join; family: tpch
-- source: SQLStorm v1.0/tpch/queries/25509.sql
-- semantic_filter: sqlstorm_order_period; tier=low; SQLStorm 25509 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (((((part p INNER JOIN partsupp ps ON p.p_partkey = ps.ps_partkey) LEFT OUTER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) RIGHT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) INNER JOIN customer c ON o.o_custkey = c.c_custkey)
WHERE o.o_orderdate BETWEEN DATE '1996-01-01' AND DATE '1996-03-15';
