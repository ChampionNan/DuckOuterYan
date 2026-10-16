-- query_type: join; family: tpch
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- semantic_filter: sqlstorm_shipment_period; tier=medium; SQLStorm 17751 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((supplier s LEFT OUTER JOIN partsupp ps ON ps.ps_suppkey = s.s_suppkey) INNER JOIN (lineitem l RIGHT OUTER JOIN part p ON p.p_partkey = l.l_partkey) ON p.p_partkey = ps.ps_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-12-31';
