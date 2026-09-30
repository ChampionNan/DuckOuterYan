-- Audit deliveries received more than 100 days after the committed date.
-- Derived from the Q21 delivery-date relation with a stricter severity threshold.
-- One comparison per filtered relation; original join conditions are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate - l_commitdate > 100
) ON c_custkey = o_custkey;
