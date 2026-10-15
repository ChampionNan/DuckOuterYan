-- Audit deliveries received more than three calendar months after the committed date.
-- Calendar-month addition differs from a fixed 90-day duration around month boundaries.
-- Keep customers without qualifying lines; original join conditions are unchanged.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate > l_commitdate + INTERVAL '3 months'
) ON c_custkey = o_custkey;
