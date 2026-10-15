-- Fully shipped orders with line items shipped before the 1993 reporting cutoff.
-- Preserve all customers, including those without a qualifying order line.
-- One unary predicate per filtered relation; customer and join keys are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate < DATE '1993-01-01'
) ON c_custkey = o_custkey;
