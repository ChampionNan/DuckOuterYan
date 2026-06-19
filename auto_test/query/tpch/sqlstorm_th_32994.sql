WITH RECURSIVE SupplierHierarchy AS (
    SELECT s_suppkey, s_name, s_address, s_nationkey, 
           0 AS level
    FROM supplier
    WHERE s_nationkey IN (SELECT n_nationkey 
                          FROM nation 
                          WHERE n_name = 'USA')
    UNION ALL
    SELECT s.s_suppkey, s.s_name, s.s_address, s.s_nationkey, 
           sh.level + 1
    FROM supplier s
    JOIN SupplierHierarchy sh ON s.s_nationkey = sh.s_suppkey
)
, PartAvailability AS (
    SELECT ps.ps_partkey, SUM(ps.ps_availqty) AS total_available
    FROM partsupp ps
    GROUP BY ps.ps_partkey
)
, OrderSummary AS (
    SELECT o.o_orderkey, o.o_totalprice, 
           SUM(l.l_quantity) OVER (PARTITION BY o.o_orderkey) AS total_items
    FROM orders o
    JOIN lineitem l ON o.o_orderkey = l.l_orderkey
    WHERE o.o_orderdate >= '1997-01-01'
)

SELECT 
    p.p_partkey,
    p.p_name,
    COALESCE(sa.total_available, 0) AS available_quantity,
    os.total_items AS items_in_order,
    ROW_NUMBER() OVER (PARTITION BY p.p_partkey ORDER BY os.o_totalprice DESC) AS rank,
    CONCAT('Part ', p.p_name, ' from ', s.s_name) AS supplier_info,
    CASE 
        WHEN os.total_items IS NULL THEN 'No orders found'
        ELSE 'Order present'
    END AS order_status
FROM part p
LEFT JOIN PartAvailability sa ON p.p_partkey = sa.ps_partkey
LEFT JOIN OrderSummary os ON sa.ps_partkey = os.o_orderkey
LEFT JOIN supplier s ON sa.ps_partkey = s.s_suppkey
WHERE p.p_retailprice > 20.00 AND (p.p_comment LIKE '%fragile%' OR p.p_size > 10);
