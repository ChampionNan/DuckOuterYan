-- Audit deliveries received more than 90 days after the committed date.
-- DATE subtraction expresses the delay as a number of days without a TIMESTAMP cast.
-- Derived from the Q21 delivery-date relation with a severity threshold.
-- One comparison per filtered relation; original join conditions are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey;
