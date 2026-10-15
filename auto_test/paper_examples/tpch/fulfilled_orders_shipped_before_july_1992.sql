-- Audit shipments dispatched before July 1992 from fully shipped orders.
-- The order status uses the Q21 convention; the shipment-date cutoff follows
-- the date-filter style of Q6. This is a three-table outer-join variant.
-- Keep customer unfiltered and retain the original join conditions.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate < DATE '1992-07-01'
) ON c_custkey = o_custkey;
