-- query_type: aggregate; family: tpch
-- source: TPC-H Q3
-- semantic_filter: tpch_order_deadline; tier=low; TPC-H Q3 orders booked before a reporting deadline
-- predicate: o.o_orderdate < DATE '1992-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT c.c_custkey AS group_key, SUM(o.o_custkey) AS key_sum
FROM (lineitem l FULL OUTER JOIN (orders o RIGHT OUTER JOIN customer c ON c.c_custkey = o.o_custkey) ON o.o_orderkey = l.l_orderkey)
WHERE o.o_orderdate < DATE '1992-03-15'
GROUP BY c.c_custkey;
