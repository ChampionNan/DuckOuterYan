WITH RankedSuppliers AS (
    SELECT 
        s.s_suppkey, 
        s.s_name, 
        s.s_acctbal, 
        ROW_NUMBER() OVER (PARTITION BY n.n_name ORDER BY s.s_acctbal DESC) AS rank,
        n.n_name AS nation_name
    FROM 
        supplier s
    JOIN 
        nation n ON s.s_nationkey = n.n_nationkey
),

TotalSales AS (
    SELECT 
        l.l_partkey, 
        SUM(l.l_extendedprice * (1 - l.l_discount)) AS total_sales
    FROM 
        lineitem l
    WHERE 
        l.l_shipdate >= DATE '1997-01-01' 
        AND l.l_shipdate < DATE '1998-01-01'
    GROUP BY 
        l.l_partkey
),

PartDetails AS (
    SELECT 
        p.p_partkey,
        p.p_name,
        p.p_brand,
        p.p_retailprice,
        COALESCE(ps.ps_availqty, 0) AS available_quantity,
        (p.p_retailprice * COALESCE(ps.ps_availqty, 0)) AS total_value
    FROM 
        part p
    LEFT JOIN 
        partsupp ps ON p.p_partkey = ps.ps_partkey
)

SELECT 
    r.region_name,
    pd.p_name,
    pd.p_brand,
    pd.available_quantity,
    td.total_sales,
    rs.s_name AS top_supplier
FROM 
    (SELECT r.r_name AS region_name, n.n_name
    FROM region r
    JOIN nation n ON r.r_regionkey = n.n_regionkey) r
JOIN 
    PartDetails pd ON pd.p_partkey IN (SELECT ps.ps_partkey FROM partsupp ps 
                                         JOIN supplier s ON ps.ps_suppkey = s.s_suppkey 
                                         WHERE s.s_nationkey = (SELECT n.n_nationkey FROM nation n WHERE n.n_name = r.n_name))
LEFT JOIN 
    TotalSales td ON pd.p_partkey = td.l_partkey
LEFT JOIN 
    RankedSuppliers rs ON rs.rank = 1 AND rs.nation_name = r.n_name
WHERE 
    pd.total_value > 10000.00;
