-- Fully shipped order lines with a commitment date before July 1992.
-- Preserve all customers, including those without a qualifying order line.
-- One unary predicate per filtered relation; customer and join keys are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey;
