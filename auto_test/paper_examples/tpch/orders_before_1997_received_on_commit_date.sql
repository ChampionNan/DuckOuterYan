-- Orders placed before the 1997 reporting cutoff, with receipt exactly on
-- the committed date. Preserve customers without qualifying order lines.
-- Q3 supplies the order-date cutoff pattern; its original date is 1995-03-15.
-- Q21 compares receipt and commit dates using >; equality is a business variant.
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate = l_commitdate
) ON c_custkey = o_custkey;
