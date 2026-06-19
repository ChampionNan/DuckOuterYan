
WITH StringBenchmark AS (
    SELECT 
        ca.ca_address_id,
        CONCAT(ca.ca_street_number, ' ', ca.ca_street_name, ' ', ca.ca_street_type) AS Full_Address,
        LEFT(ca.ca_city, 10) AS Short_City,
        RIGHT(ca.ca_zip, 5) AS Zip_Code,
        LENGTH(ca.ca_country) AS Country_Length,
        STRING_AGG(CONCAT(cd.cd_gender, '_', cd.cd_marital_status), ', ') AS Demographics,
        CASE 
            WHEN LENGTH(ca.ca_zip) < 5 THEN 'Invalid ZIP'
            ELSE 'Valid ZIP'
        END AS Zip_Validation
    FROM 
        customer_address ca
    LEFT JOIN 
        customer c ON ca.ca_address_sk = c.c_current_addr_sk
    LEFT JOIN 
        customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    WHERE 
        ca.ca_country LIKE '%United%'
    GROUP BY 
        ca.ca_address_id, ca.ca_street_number, ca.ca_street_name, ca.ca_street_type, ca.ca_city, ca.ca_zip, ca.ca_country
)
SELECT 
    Full_Address,
    Short_City,
    Zip_Code,
    Country_Length,
    Demographics,
    Zip_Validation
FROM 
    StringBenchmark;
