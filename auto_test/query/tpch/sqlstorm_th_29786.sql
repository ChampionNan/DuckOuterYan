WITH String_Benchmark AS (
    SELECT 
        p.p_partkey,
        p.p_name,
        p.p_comment,
        LENGTH(p.p_name) AS name_length,
        LENGTH(p.p_comment) AS comment_length,
        CONCAT(p.p_name, ' - ', p.p_comment) AS combined_string,
        UPPER(p.p_name) AS upper_name,
        LOWER(p.p_comment) AS lower_comment
    FROM 
        part p
    WHERE 
        p.p_size > 10
),
Supplier_Info AS (
    SELECT 
        s.s_suppkey,
        s.s_name,
        s.s_nationkey,
        n.n_name AS nation_name,
        LENGTH(s.s_name) AS supplier_name_length,
        SUBSTRING(s.s_comment, 1, 30) AS short_comment
    FROM 
        supplier s
    JOIN 
        nation n ON s.s_nationkey = n.n_nationkey
),
Combined_Stats AS (
    SELECT 
        b.p_partkey,
        b.name_length,
        b.comment_length,
        b.combined_string,
        b.upper_name,
        b.lower_comment,
        s.s_suppkey,
        s.supplier_name_length,
        s.nation_name,
        s.short_comment
    FROM 
        String_Benchmark b
    LEFT JOIN 
        Supplier_Info s ON b.p_partkey % 10 = s.s_suppkey % 10
)
SELECT 
    c.c_custkey,
    c.c_name,
    cs.*,
    COUNT(DISTINCT o.o_orderkey) AS order_count
FROM 
    customer c
JOIN 
    Combined_Stats cs ON cs.nation_name = (SELECT r_name FROM region r WHERE r.r_regionkey = (SELECT n.n_regionkey FROM nation n WHERE n.n_nationkey = c.c_nationkey))
LEFT JOIN 
    orders o ON o.o_custkey = c.c_custkey
GROUP BY 
    c.c_custkey, c.c_name, cs.p_partkey, cs.name_length, cs.comment_length, cs.combined_string, cs.upper_name, cs.lower_comment, cs.s_suppkey, cs.supplier_name_length, cs.nation_name, cs.short_comment;
