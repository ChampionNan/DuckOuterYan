-- Audit severe delivery delays for orders placed before July 1998.
-- The receipt occurred more than 100 days after the committed date.
-- Derived from the Q3 order-date cutoff and Q21 delivery-date relation;
-- the report cutoff and 100-day severity threshold are example parameters.
-- One comparison per filtered relation; original join conditions are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate - l_commitdate > 100
) ON c_custkey = o_custkey;
