
WITH RankedOrders AS (
    SELECT 
        o.o_orderkey,
        o.o_orderdate,
        SUM(l.l_extendedprice * (1 - l.l_discount)) AS total_revenue,
        ROW_NUMBER() OVER (PARTITION BY o.o_orderkey ORDER BY o.o_orderdate DESC) AS order_rank
    FROM 
        orders o
    JOIN 
        lineitem l ON o.o_orderkey = l.l_orderkey
    WHERE 
        o.o_orderdate >= '1996-01-01' AND o.o_orderdate <= '1996-12-31'
    GROUP BY 
        o.o_orderkey, o.o_orderdate
),
TopOrders AS (
    SELECT 
        r.o_orderkey,
        r.o_orderdate,
        r.total_revenue,
        RANK() OVER (ORDER BY r.total_revenue DESC) AS revenue_rank
    FROM 
        RankedOrders r
)
SELECT 
    o.o_orderkey,
    o.o_orderdate,
    o.total_revenue,
    COALESCE(c.c_name, 'N/A') AS customer_name,
    COALESCE(s.s_name, 'N/A') AS supplier_name,
    CASE 
        WHEN o.total_revenue > 10000 THEN 'High Value'
        WHEN o.total_revenue BETWEEN 5000 AND 10000 THEN 'Medium Value'
        ELSE 'Low Value'
    END AS revenue_category
FROM 
    TopOrders o
LEFT JOIN 
    customer c ON c.c_custkey = (
        SELECT c.c_custkey 
        FROM orders 
        WHERE o.o_orderkey = c.c_custkey 
        ORDER BY o.o_orderdate DESC 
        LIMIT 1)
LEFT JOIN 
    partsupp ps ON ps.ps_partkey = (
        SELECT l.l_partkey 
        FROM lineitem l 
        WHERE l.l_orderkey = o.o_orderkey 
        ORDER BY l.l_extendedprice DESC 
        LIMIT 1)
LEFT JOIN 
    supplier s ON s.s_suppkey = ps.ps_suppkey
WHERE 
    o.revenue_rank <= 10;
