
WITH Customer_Info AS (
    SELECT 
        c.c_customer_sk,
        CONCAT(c.c_first_name, ' ', c.c_last_name) AS full_name,
        ca.ca_city,
        ca.ca_state,
        cd.cd_gender,
        CASE 
            WHEN cd.cd_marital_status = 'M' THEN 'Married'
            WHEN cd.cd_marital_status = 'S' THEN 'Single'
            ELSE 'Other' 
        END AS marital_status,
        ARRAY_AGG(DISTINCT i.i_product_name) AS purchased_items
    FROM 
        customer c
    JOIN 
        customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
    JOIN 
        customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    LEFT JOIN 
        store_sales ss ON c.c_customer_sk = ss.ss_customer_sk
    LEFT JOIN 
        item i ON ss.ss_item_sk = i.i_item_sk
    GROUP BY 
        c.c_customer_sk, c.c_first_name, c.c_last_name, ca.ca_city, ca.ca_state, cd.cd_gender, cd.cd_marital_status
),
Benchmark AS (
    SELECT 
        full_name,
        ca_city,
        ca_state,
        cd_gender,
        marital_status,
        TRIM(REPLACE(ARRAY_TO_STRING(purchased_items, ', '), ' ', '_')) AS formatted_items,
        LENGTH(TRIM(REPLACE(ARRAY_TO_STRING(purchased_items, ', '), ' ', '_'))) AS item_length
    FROM 
        Customer_Info
)
SELECT 
    full_name,
    ca_city,
    ca_state,
    cd_gender,
    marital_status,
    formatted_items,
    item_length
FROM 
    Benchmark
WHERE 
    item_length > 50;
