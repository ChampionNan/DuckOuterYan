WITH RECURSIVE supplier_summary AS (
    SELECT s.s_suppkey, s.s_name, s.s_acctbal, 0 AS level, CAST(s.s_name AS VARCHAR(255)) AS hierarchy
    FROM supplier s
    WHERE s.s_acctbal IS NOT NULL AND s.s_acctbal > 0
    UNION ALL
    SELECT supp.s_suppkey, supp.s_name, supp.s_acctbal, ss.level + 1, CAST(ss.hierarchy || ' > ' || supp.s_name AS VARCHAR(255))
    FROM supplier supp
    JOIN supplier_summary ss ON supp.s_nationkey = ss.s_suppkey
    WHERE ss.level < 5
),
top_suppliers AS (
    SELECT ss.s_suppkey, ss.s_name, ss.s_acctbal, ss.hierarchy
    FROM supplier_summary ss
    WHERE ss.level = 0
    ORDER BY ss.s_acctbal DESC
    LIMIT 10
),
part_details AS (
    SELECT p.p_partkey, p.p_name, p.p_retailprice, ps.ps_supplycost,
           (p.p_retailprice - ps.ps_supplycost) / p.p_retailprice * 100 AS profit_margin
    FROM part p
    JOIN partsupp ps ON p.p_partkey = ps.ps_partkey
    WHERE ps.ps_availqty > 0
),
customer_orders AS (
    SELECT c.c_custkey, c.c_name, c.c_acctbal, COUNT(o.o_orderkey) AS order_count
    FROM customer c
    LEFT JOIN orders o ON c.c_custkey = o.o_custkey
    WHERE c.c_acctbal IS NOT NULL AND c.c_acctbal < 1000
    GROUP BY c.c_custkey, c.c_name, c.c_acctbal
),
ranked_orders AS (
    SELECT co.c_custkey, co.order_count, 
           RANK() OVER (PARTITION BY co.order_count ORDER BY co.c_acctbal DESC) AS order_rank
    FROM customer_orders co
)
SELECT DISTINCT rs.s_name, 
       pd.p_name,
       pd.profit_margin,
       CASE 
           WHEN co.order_count IS NULL THEN 'No Orders'
           WHEN co.order_count > 5 THEN 'High Activity'
           ELSE 'Low Activity'
       END AS activity_status
FROM top_suppliers rs
LEFT JOIN part_details pd ON rs.s_suppkey = pd.p_partkey
FULL OUTER JOIN ranked_orders co ON rs.s_suppkey = co.c_custkey
WHERE pd.profit_margin > 0.5
  OR rs.s_acctbal IS NULL
  OR NOT EXISTS (SELECT 1 FROM lineitem l WHERE l.l_orderkey IN (SELECT o.o_orderkey FROM orders o WHERE o.o_custkey = co.c_custkey));
