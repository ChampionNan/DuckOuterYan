-- query_type: aggregate; family: tpch
-- source: SQLStorm v1.0/tpch/queries/17751.sql
-- semantic_filter: sqlstorm_shipment_period; tier=low; SQLStorm 17751 shipment reporting period
-- predicate: l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT p.p_partkey AS group_key, MIN(ps.ps_partkey) AS min_key
FROM ((part p LEFT OUTER JOIN lineitem l ON p.p_partkey = l.l_partkey) FULL OUTER JOIN (partsupp ps INNER JOIN supplier s ON ps.ps_suppkey = s.s_suppkey) ON p.p_partkey = ps.ps_partkey)
WHERE l.l_shipdate BETWEEN DATE '1997-01-01' AND DATE '1997-03-15'
GROUP BY p.p_partkey;
