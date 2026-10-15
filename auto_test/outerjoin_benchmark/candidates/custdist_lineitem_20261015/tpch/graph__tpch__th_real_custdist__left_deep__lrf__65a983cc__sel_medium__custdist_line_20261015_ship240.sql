-- Independent G-H-LD-05 shipment-date candidate; pending CPU9 measurement.
-- Four relations and LRF expression retained; orders and lineitem input predicates.
-- New predicate changes the workload; not equivalent to the active query.
SELECT *
FROM customer
    LEFT OUTER JOIN (SELECT * FROM orders WHERE o_orderdate BETWEEN DATE '1992-01-01' AND DATE '1994-04-19') AS orders ON c_custkey = o_custkey
    RIGHT OUTER JOIN (SELECT * FROM lineitem WHERE l_shipdate BETWEEN DATE '1992-01-01' AND DATE '1992-08-27') AS lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE orders.o_orderdate BETWEEN DATE '1992-01-01' AND DATE '1994-04-19'
  AND lineitem.l_shipdate BETWEEN DATE '1992-01-01' AND DATE '1992-08-27';
