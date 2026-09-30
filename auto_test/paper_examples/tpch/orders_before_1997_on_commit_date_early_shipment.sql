-- Orders placed before 1997, shipped before the committed date, and received
-- exactly on that date. Preserve customers without qualifying order lines.
-- The shipment predicate is taken directly from TPC-H Q12.
-- Under dbgen's receipt > shipment invariant, it does not further filter
-- rows already satisfying receipt = commit; it is not a general SQL identity.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate = l_commitdate
       AND l_shipdate < l_commitdate
) ON c_custkey = o_custkey;
