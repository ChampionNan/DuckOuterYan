
WITH RECURSIVE income_ranges AS (
    SELECT ib_income_band_sk, ib_lower_bound, ib_upper_bound
    FROM income_band
    WHERE ib_lower_bound IS NOT NULL
    UNION ALL
    SELECT ib_income_band_sk, ib_lower_bound + 10, ib_upper_bound + 10
    FROM income_ranges
    WHERE ib_upper_bound < 1000
),
customer_data AS (
    SELECT c.c_customer_sk, c.c_customer_id, cd.cd_gender, 
           CASE 
               WHEN cd.cd_marital_status = 'M' THEN 'Married'
               WHEN cd.cd_marital_status IS NULL THEN 'Unknown'
               ELSE 'Single'
           END AS marital_status,
           COUNT(DISTINCT cr.cr_order_number) AS total_returns
    FROM customer c
    LEFT JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    LEFT JOIN catalog_returns cr ON c.c_customer_sk = cr.cr_returning_customer_sk
    GROUP BY c.c_customer_sk, c.c_customer_id, cd.cd_gender, cd.cd_marital_status
),
ordered_customers AS (
    SELECT c.*, 
           DENSE_RANK() OVER (PARTITION BY marital_status ORDER BY total_returns DESC) AS rank_within_marital_status
    FROM customer_data c
),
joined_data AS (
    SELECT oc.*, 
           i.ib_income_band_sk, 
           i.ib_lower_bound, 
           i.ib_upper_bound
    FROM ordered_customers oc
    LEFT JOIN income_ranges i ON oc.total_returns BETWEEN i.ib_lower_bound AND i.ib_upper_bound
),
final_output AS (
    SELECT j.*, 
           COALESCE(j.ib_income_band_sk, 0) AS income_band_id, 
           ROW_NUMBER() OVER (PARTITION BY j.marital_status ORDER BY j.total_returns DESC) AS rank 
    FROM joined_data j
)
SELECT f.c_customer_id, f.cd_gender, f.marital_status, 
       f.income_band_id, f.total_returns, f.rank 
FROM final_output f
WHERE f.rank <= 5
  AND (f.total_returns > 0 OR f.total_returns IS NULL);
