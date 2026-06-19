
WITH RECURSIVE CTE_Suppliers AS (
    SELECT s_suppkey, s_name, s_acctbal, s_comment, 1 AS level
    FROM supplier
    WHERE s_acctbal > 1000
    UNION ALL
    SELECT s.s_suppkey, s.s_name, s.s_acctbal, s.s_comment, cs.level + 1
    FROM supplier s
    INNER JOIN CTE_Suppliers cs ON s.s_suppkey = cs.s_suppkey
    WHERE cs.level < 3
),
OrderAmounts AS (
    SELECT o.o_orderkey, o.o_orderdate, SUM(l.l_extendedprice * (1 - l.l_discount)) AS total_amount
    FROM orders o
    JOIN lineitem l ON o.o_orderkey = l.l_orderkey
    GROUP BY o.o_orderkey, o.o_orderdate
),
RankedOrders AS (
    SELECT oa.o_orderkey, oa.o_orderdate, oa.total_amount,
           RANK() OVER (PARTITION BY oa.o_orderdate ORDER BY oa.total_amount DESC) AS rnk
    FROM OrderAmounts oa
    JOIN orders o ON oa.o_orderkey = o.o_orderkey
),
SupplierParts AS (
    SELECT ps.ps_partkey, ps.ps_supplycost, p.p_brand, p.p_type,
           ROW_NUMBER() OVER (PARTITION BY p.p_brand ORDER BY ps.ps_supplycost DESC) AS rn
    FROM partsupp ps
    JOIN part p ON ps.ps_partkey = p.p_partkey
)
SELECT s.s_name, s.s_acctbal, r.o_orderkey, r.o_orderdate, r.total_amount,
       COALESCE(sp.ps_supplycost, 0) AS supply_cost, 
       CASE 
           WHEN r.rnk = 1 THEN 'Top Order'
           ELSE 'Regular Order'
       END AS order_type
FROM CTE_Suppliers s
FULL OUTER JOIN RankedOrders r ON s.s_suppkey = r.o_orderkey
LEFT JOIN SupplierParts sp ON sp.ps_partkey = r.o_orderkey
WHERE s.s_acctbal IS NOT NULL AND r.total_amount > 5000;
