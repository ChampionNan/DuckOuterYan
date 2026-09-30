-- Orders placed before the TPC-H Q3 cutoff, with receipt on the committed date.
-- Preserve customers without qualifying order lines. This is a business variant, not Q3.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1995-03-15'
       AND l_receiptdate = l_commitdate
) ON c_custkey = o_custkey;
