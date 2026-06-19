WITH RankedSales AS (
    SELECT 
        ws.ws_item_sk,
        ws.ws_order_number,
        ws.ws_sales_price,
        ws.ws_net_profit,
        ROW_NUMBER() OVER (PARTITION BY ws.ws_item_sk ORDER BY ws.ws_net_profit DESC) AS rnk
    FROM 
        web_sales ws
    WHERE 
        ws.ws_sales_price IS NOT NULL 
        AND ws.ws_quantity > 0
),
CustomerInfo AS (
    SELECT 
        c.c_customer_id,
        cd.cd_gender,
        COALESCE(cd.cd_marital_status, 'Unknown') AS marital_status,
        hd.hd_income_band_sk,
        SUM(CASE WHEN ws.ws_sales_price > 100 THEN 1 ELSE 0 END) AS high_value_purchases
    FROM 
        customer c
    LEFT JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    LEFT JOIN household_demographics hd ON hd.hd_demo_sk = c.c_current_hdemo_sk
    LEFT JOIN web_sales ws ON c.c_customer_sk = ws.ws_bill_customer_sk
    GROUP BY 
        c.c_customer_id, cd.cd_gender, marital_status, hd.hd_income_band_sk
)
SELECT 
    ci.c_customer_id,
    ci.cd_gender,
    ci.marital_status,
    ib.ib_lower_bound,
    ib.ib_upper_bound,
    COALESCE(rk.ws_item_sk, 0) AS item_sk,
    COALESCE(rk.ws_order_number, 0) AS order_number,
    COALESCE(rk.ws_sales_price, 0) AS sales_price,
    COALESCE(rk.ws_net_profit, 0) AS net_profit,
    ci.high_value_purchases
FROM 
    CustomerInfo ci
LEFT JOIN RankedSales rk ON ci.hd_income_band_sk = rk.ws_item_sk % 10  
LEFT JOIN income_band ib ON ci.hd_income_band_sk = ib.ib_income_band_sk
WHERE 
    (ci.high_value_purchases > 0 OR ci.cd_gender = 'M') 
    AND ci.marital_status IS NOT NULL;
