-- Audit deliveries received more than 90 days after the committed date,
-- for orders placed before 1997, preserving customers without such lines.
-- A severity threshold added to the Q21 date relation; not an official Q21 predicate.
-- Each filtered relation has one comparison; original join conditions are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate > l_commitdate + INTERVAL '90 days'
) ON c_custkey = o_custkey;
