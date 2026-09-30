-- Audit cross-year shipments received on their committed date, for orders placed before 1997.
-- Preserve customers with no qualifying order line.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate = l_commitdate
       AND EXTRACT(YEAR FROM l_shipdate) < EXTRACT(YEAR FROM l_receiptdate)
) ON c_custkey = o_custkey;
