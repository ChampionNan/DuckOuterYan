WITH RankedSuppliers AS (
    SELECT
        s.s_suppkey,
        s.s_name,
        s.s_acctbal,
        RANK() OVER (PARTITION BY ps_partkey ORDER BY s.s_acctbal DESC) AS supplier_rank
    FROM
        supplier s
    JOIN
        partsupp ps ON s.s_suppkey = ps.ps_suppkey
    WHERE
        s.s_acctbal > 0
),
TotalSales AS (
    SELECT
        l.l_partkey,
        SUM(l.l_extendedprice * (1 - l.l_discount)) AS total_revenue
    FROM
        lineitem l
    WHERE
        l.l_shipdate >= DATE '1994-01-01' AND l.l_shipdate < DATE '1995-01-01'
    GROUP BY
        l.l_partkey
),
TopSellingParts AS (
    SELECT
        p.p_partkey,
        p.p_name,
        COALESCE(ts.total_revenue, 0) AS total_revenue,
        ROW_NUMBER() OVER (ORDER BY COALESCE(ts.total_revenue, 0) DESC) AS revenue_rank
    FROM
        part p
    LEFT JOIN
        TotalSales ts ON p.p_partkey = ts.l_partkey
)
SELECT
    p.p_partkey,
    p.p_name,
    s.s_name AS top_supplier,
    ts.total_revenue,
    p.p_retailprice,
    CASE 
        WHEN ts.total_revenue IS NULL THEN 'No Sales'
        ELSE 'Sold'
    END AS sales_status
FROM
    TopSellingParts ts
LEFT JOIN
    RankedSuppliers s ON s.s_suppkey = (
        SELECT 
            ps.ps_suppkey
        FROM 
            partsupp ps
        WHERE 
            ps.ps_partkey = ts.p_partkey
        ORDER BY 
            s_acctbal DESC
        LIMIT 1
    )
JOIN
    part p ON ts.p_partkey = p.p_partkey
WHERE
    ts.revenue_rank <= 10;
