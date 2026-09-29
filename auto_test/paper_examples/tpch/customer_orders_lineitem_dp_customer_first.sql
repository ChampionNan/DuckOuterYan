-- Unary-only variant: remove l_shipmode = 'AIR'; keep both join keys and dates.
-- DP chooses customer-orders first. The original SJ weight 1.0 rejects it;
-- the paper experiment's weight 0.20 admits it through the normal cost gate.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1995-01-01'
       AND o_orderdate < DATE '1996-01-01'
) ON c_custkey = o_custkey;
