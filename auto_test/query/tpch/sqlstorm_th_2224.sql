
WITH RankedSuppliers AS (
    SELECT 
        s.s_suppkey,
        s.s_name,
        s.s_acctbal,
        ROW_NUMBER() OVER (PARTITION BY p.p_partkey ORDER BY s.s_acctbal DESC) AS rn
    FROM 
        supplier s
    JOIN 
        partsupp ps ON s.s_suppkey = ps.ps_suppkey
    JOIN 
        part p ON ps.ps_partkey = p.p_partkey
    WHERE 
        s.s_acctbal IS NOT NULL AND s.s_acctbal > 1000
), CustomerOrders AS (
    SELECT 
        c.c_custkey,
        c.c_name,
        SUM(o.o_totalprice) AS total_spent
    FROM 
        customer c
    JOIN 
        orders o ON c.c_custkey = o.o_custkey
    GROUP BY 
        c.c_custkey, c.c_name
), AllData AS (
    SELECT 
        p.p_name,
        p.p_brand,
        COALESCE(rs.rn, 0) AS supplier_rank,
        COALESCE(co.total_spent, 0) AS customer_spent,
        CASE
            WHEN COALESCE(co.total_spent, 0) > 5000 THEN 'High Roller'
            WHEN COALESCE(co.total_spent, 0) BETWEEN 1000 AND 5000 THEN 'Mid Tier'
            ELSE 'Low Tier'
        END AS customer_tier,
        p.p_partkey
    FROM 
        part p
    LEFT JOIN 
        RankedSuppliers rs ON p.p_partkey = rs.s_suppkey
    LEFT JOIN 
        CustomerOrders co ON co.c_custkey = (
            SELECT o.o_custkey 
            FROM orders o 
            JOIN lineitem l ON o.o_orderkey = l.l_orderkey
            WHERE l.l_partkey = p.p_partkey 
            ORDER BY o.o_orderdate DESC
            LIMIT 1
        )
)
SELECT 
    d.p_name,
    d.p_brand,
    d.supplier_rank,
    d.customer_spent,
    d.customer_tier
FROM 
    AllData d
JOIN 
    part p ON d.p_partkey = p.p_partkey
WHERE 
    d.supplier_rank <= 5;
