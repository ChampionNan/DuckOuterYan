WITH RankedOrders AS (
    SELECT 
        o.o_orderkey,
        o.o_orderdate,
        o.o_totalprice,
        RANK() OVER (PARTITION BY o.o_orderstatus ORDER BY o.o_totalprice DESC) AS order_rank
    FROM 
        orders o
    WHERE 
        o.o_orderdate >= '1997-01-01' 
        AND o.o_orderdate < '1998-01-01'
),
SupplierCosts AS (
    SELECT 
        ps.ps_partkey,
        SUM(ps.ps_supplycost) AS total_cost
    FROM 
        partsupp ps
    GROUP BY 
        ps.ps_partkey
),
CustomerInfo AS (
    SELECT 
        c.c_custkey,
        c.c_name,
        c.c_acctbal,
        CASE 
            WHEN c.c_acctbal IS NULL THEN 'No Balance' 
            WHEN c.c_acctbal BETWEEN 0 AND 1000 THEN 'Low Balance'
            WHEN c.c_acctbal BETWEEN 1001 AND 10000 THEN 'Medium Balance'
            ELSE 'High Balance' 
        END AS balance_category
    FROM 
        customer c
),
PartDetails AS (
    SELECT 
        p.p_partkey,
        p.p_name,
        p.p_retailprice,
        CASE 
            WHEN p.p_retailprice IS NULL THEN 'Unknown Price' 
            ELSE 'Known Price'
        END AS price_status
    FROM 
        part p
)
SELECT 
    ci.c_name,
    ci.balance_category,
    o.o_orderkey,
    o.o_orderdate,
    o.o_totalprice,
    pd.p_name,
    pd.price_status,
    sc.total_cost,
    ROW_NUMBER() OVER (PARTITION BY ci.balance_category ORDER BY o.o_totalprice DESC) AS cust_order_rank
FROM 
    RankedOrders o
JOIN 
    CustomerInfo ci ON o.o_orderkey = (SELECT o2.o_orderkey FROM orders o2 WHERE o2.o_custkey = ci.c_custkey LIMIT 1)
LEFT JOIN 
    lineitem l ON o.o_orderkey = l.l_orderkey
LEFT JOIN 
    PartDetails pd ON l.l_partkey = pd.p_partkey
LEFT JOIN 
    SupplierCosts sc ON pd.p_partkey = sc.ps_partkey
WHERE 
    (ci.c_acctbal IS NOT NULL AND ci.c_acctbal > 500) 
    OR (ci.c_name LIKE 'A%' AND pd.p_retailprice IS NULL);
