
WITH RankedSuppliers AS (
    SELECT 
        s.s_suppkey, 
        s.s_name, 
        s.s_acctbal,
        ROW_NUMBER() OVER (PARTITION BY p.p_partkey ORDER BY s.s_acctbal DESC) AS rnk
    FROM 
        supplier s
    JOIN 
        partsupp ps ON s.s_suppkey = ps.ps_suppkey
    JOIN 
        part p ON ps.ps_partkey = p.p_partkey
    WHERE 
        ps.ps_availqty > 0
),
RecentOrders AS (
    SELECT 
        o.o_orderkey, 
        o.o_custkey, 
        o.o_orderdate, 
        SUM(l.l_extendedprice * (1 - l.l_discount)) AS order_revenue
    FROM 
        orders o
    JOIN 
        lineitem l ON o.o_orderkey = l.l_orderkey
    WHERE 
        o.o_orderstatus IN ('F', 'P')
    AND 
        l.l_shipdate >= DATE '1998-10-01' - INTERVAL '1 year'
    GROUP BY 
        o.o_orderkey, o.o_custkey, o.o_orderdate
)
SELECT 
    p.p_partkey,
    p.p_name,
    p.p_size,
    s.rnk,
    COALESCE(ro.order_revenue, 0) AS total_revenue,
    CASE 
        WHEN s.s_acctbal IS NULL THEN 'No Supplier'
        ELSE s.s_name 
    END AS supplier_name
FROM 
    part p
LEFT JOIN 
    RankedSuppliers s ON s.rnk = 1 AND s.s_suppkey = (
        SELECT ps.ps_suppkey 
        FROM partsupp ps 
        WHERE ps.ps_partkey = p.p_partkey 
        ORDER BY ps.ps_supplycost ASC 
        FETCH FIRST 1 ROW ONLY
    )
LEFT JOIN 
    RecentOrders ro ON ro.o_custkey = (
        SELECT c.c_custkey 
        FROM customer c 
        WHERE c.c_nationkey = (
            SELECT n.n_nationkey 
            FROM nation n 
            WHERE n.n_name = 'USA'
        )
        FETCH FIRST 1 ROW ONLY
    )
WHERE 
    p.p_size IN (SELECT DISTINCT p_size FROM part WHERE p_retailprice > 200);
