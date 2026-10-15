-- CPU8 SF100 semantic candidates A-O. Each query retains customers without matching qualifying items.

-- A: phone13_july1998_commitjuly1992
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- B: building_july1998_commitjuly1992
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING';

-- C: phone13_order_before_july1998_late100
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate - l_commitdate > 100
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- D: building_order_before_july1998_late90
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING';

-- E: phone13_control_f_ship1993
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_shipdate < DATE '1993-01-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- F: phone_q2_1992_commit
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1992-04-01'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- G: building_q2_1992_commit
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1992-04-01'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING';

-- H: phone_fiscal1992_commit
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate >= DATE '1992-04-01'
       AND l_commitdate < DATE '1993-04-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- I: phone_beforejuly1998_late90
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1998-07-01'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- J: phone_before1997_late90
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- K: building_before1997_late90
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey
WHERE c_mktsegment = 'BUILDING';

-- L: phone_fullyshipped_late90
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderstatus = 'F'
       AND l_receiptdate - l_commitdate > 90
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- M: phone_before1997_late3months
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderdate < DATE '1997-01-01'
       AND l_receiptdate > l_commitdate + INTERVAL '3 months'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- N: phone_q13_commitjuly1992
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_comment NOT LIKE '%special%requests%'
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';

-- O: phone_urgenthigh_commitjuly1992
SELECT c_name, o_orderkey, l_extendedprice
FROM customer
LEFT OUTER JOIN (
    orders JOIN lineitem
        ON o_orderkey = l_orderkey
       AND o_orderpriority IN ('1-URGENT', '2-HIGH')
       AND l_commitdate < DATE '1992-07-01'
) ON c_custkey = o_custkey
WHERE c_phone LIKE '13%';
