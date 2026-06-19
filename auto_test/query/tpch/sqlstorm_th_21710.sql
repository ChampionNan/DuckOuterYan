
WITH RankedSuppliers AS (
    SELECT 
        s.s_suppkey,
        s.s_name,
        RANK() OVER (PARTITION BY n.n_name ORDER BY s.s_acctbal DESC) AS supplier_rank,
        n.n_name AS nation_name
    FROM 
        supplier s
    JOIN 
        nation n ON s.s_nationkey = n.n_nationkey
), 
PartSelection AS (
    SELECT 
        p.p_partkey,
        p.p_name,
        p.p_retailprice,
        COALESCE(SUM(l.l_quantity * l.l_discount), 0) AS total_discount_qty
    FROM 
        part p
    LEFT JOIN 
        lineitem l ON p.p_partkey = l.l_partkey AND l.l_returnflag = 'N'
    GROUP BY 
        p.p_partkey, p.p_name, p.p_retailprice
), 
OrderStats AS (
    SELECT 
        o.o_orderkey, 
        o.o_orderdate,
        o.o_orderstatus,
        CASE 
            WHEN o.o_totalprice > 1000 THEN 'High Value'
            ELSE 'Standard'
        END AS order_value_category
    FROM 
        orders o
    WHERE 
        o.o_orderdate BETWEEN '1996-01-01' AND '1997-01-01'
)
SELECT 
    ps.s_suppkey,
    ps.s_name,
    p.p_name,
    p.p_retailprice,
    o.order_value_category,
    p.total_discount_qty,
    ROW_NUMBER() OVER (PARTITION BY ps.s_suppkey ORDER BY p.p_retailprice DESC) AS price_rank,
    NULLIF(p.total_discount_qty, 0) AS adjusted_discount_qty
FROM 
    RankedSuppliers ps
JOIN 
    partsupp psu ON ps.s_suppkey = psu.ps_suppkey
JOIN 
    PartSelection p ON psu.ps_partkey = p.p_partkey
LEFT JOIN 
    OrderStats o ON o.o_orderkey = (
        SELECT l.l_orderkey 
        FROM lineitem l 
        WHERE l.l_partkey = p.p_partkey 
        AND l.l_returnflag = 'N' 
        ORDER BY l.l_receiptdate DESC 
        LIMIT 1
    )
WHERE 
    ps.supplier_rank = 1 AND 
    (p.p_retailprice > 20 OR (p.p_retailprice IS NULL AND p.total_discount_qty > 0));
