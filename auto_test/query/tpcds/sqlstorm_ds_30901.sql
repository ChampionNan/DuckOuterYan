WITH RECURSIVE sales_hierarchy AS (
    SELECT 
        c.c_customer_sk,
        c.c_first_name,
        c.c_last_name,
        cd.cd_marital_status,
        cd.cd_gender,
        SUM(ws.ws_ext_sales_price) AS total_sales,
        1 AS level
    FROM 
        customer c
    JOIN 
        customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    LEFT JOIN 
        web_sales ws ON c.c_customer_sk = ws.ws_ship_customer_sk
    GROUP BY 
        c.c_customer_sk, c.c_first_name, c.c_last_name, cd.cd_marital_status, cd.cd_gender

    UNION ALL

    SELECT 
        sh.c_customer_sk,
        sh.c_first_name,
        sh.c_last_name,
        sh.cd_marital_status,
        sh.cd_gender,
        sh.total_sales * 0.9 AS total_sales,  
        sh.level + 1
    FROM 
        sales_hierarchy sh
    WHERE 
        sh.level < 3  
)
SELECT 
    s.c_customer_sk,
    s.c_first_name,
    s.c_last_name,
    s.cd_marital_status,
    s.cd_gender,
    COALESCE(s.total_sales, 0) AS total_sales,
    RANK() OVER (PARTITION BY s.cd_gender ORDER BY COALESCE(s.total_sales, 0) DESC) AS gender_rank,
    CASE 
        WHEN s.total_sales IS NULL THEN 'No Sales'
        WHEN s.total_sales = 0 THEN 'Zero Sales'
        ELSE 'Active Sales'
    END AS sales_status
FROM 
    sales_hierarchy s
LEFT JOIN 
    customer_address ca ON s.c_customer_sk = ca.ca_address_sk
WHERE 
    (ca.ca_city IS NOT NULL OR ca.ca_state IS NOT NULL)
    AND (s.total_sales IS NULL OR s.total_sales > 1000);
