WITH RECURSIVE SupplierHierarchy AS (
    SELECT s.s_suppkey, s.s_name, s.s_nationkey, 0 AS level
    FROM supplier s
    WHERE s.s_acctbal > 10000
    UNION ALL
    SELECT s.s_suppkey, s.s_name, s.s_nationkey, sh.level + 1
    FROM supplier s
    JOIN SupplierHierarchy sh ON s.s_nationkey = sh.s_nationkey
    WHERE s.s_acctbal > 5000 AND sh.level < 3
),
TopRegions AS (
    SELECT r.r_regionkey, r.r_name,
           SUM(o.o_totalprice) AS total_revenue
    FROM region r
    LEFT JOIN nation n ON r.r_regionkey = n.n_regionkey
    LEFT JOIN supplier s ON n.n_nationkey = s.s_nationkey
    LEFT JOIN partsupp ps ON s.s_suppkey = ps.ps_suppkey
    LEFT JOIN lineitem l ON ps.ps_partkey = l.l_partkey
    LEFT JOIN orders o ON l.l_orderkey = o.o_orderkey
    WHERE o.o_orderstatus = 'O' AND o.o_orderdate >= '1996-01-01'
    GROUP BY r.r_regionkey, r.r_name
),
RankedOrders AS (
    SELECT o.o_orderkey, o.o_totalprice, 
           ROW_NUMBER() OVER (PARTITION BY o.o_orderstatus ORDER BY o.o_totalprice DESC) AS rank_order
    FROM orders o
)
SELECT r.r_name, r.total_revenue, 
       COALESCE(RANK() OVER (ORDER BY r.total_revenue DESC), 0) AS revenue_rank,
       sh.s_name AS supplier_name, 
       sh.level AS supplier_level
FROM TopRegions r
LEFT JOIN SupplierHierarchy sh ON r.total_revenue > 10000
WHERE r.r_name LIKE 'North%';
