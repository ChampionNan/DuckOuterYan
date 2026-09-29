-- source: TPC-H Q3
-- transformation: connected join-subgraph adaptation; balanced mixed alternate right-deep source-derived form
-- business_semantics: TPC-H Q3 orders booked before a reporting deadline
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: tpch_order_deadline; tier=low; TPC-H Q3 orders booked before a reporting deadline
-- predicate: o.o_orderdate < DATE '1992-03-15'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (customer c LEFT OUTER JOIN (orders o RIGHT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey)
WHERE o.o_orderdate < DATE '1992-03-15';
