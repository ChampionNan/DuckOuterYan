-- Derived from TPC-H Q3: the original customer/orders/lineitem join graph.
-- Replace INNER with FULL, retain every base row and project stable row keys.
-- Remove Q3's aggregation, filters and LIMIT so the FULL boundary survives.
SELECT c.c_custkey AS customer_id, o.o_orderkey AS order_id,
       l.l_orderkey AS line_order_id, l.l_linenumber AS line_number
FROM (lineitem l FULL JOIN orders o ON l.l_orderkey = o.o_orderkey)
     FULL JOIN customer c ON o.o_custkey = c.c_custkey;
