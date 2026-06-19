
WITH AddressDetails AS (
    SELECT 
        ca_address_sk, 
        CONCAT(ca_street_number, ' ', ca_street_name, ' ', ca_street_type) AS full_address, 
        ca_city, 
        ca_state
    FROM customer_address
    WHERE ca_state IN ('CA', 'NY')
),
CustomerDetails AS (
    SELECT 
        c.c_customer_sk, 
        CONCAT(c.c_first_name, ' ', c.c_last_name) AS full_name,
        d.d_date AS last_purchase_date,
        STRING_AGG(DISTINCT CONCAT(hd.hd_buy_potential, ' - ', ib.ib_lower_bound, '-', ib.ib_upper_bound), '; ') AS income_potential
    FROM customer c
    JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
    LEFT JOIN household_demographics hd ON hd.hd_demo_sk = c.c_current_hdemo_sk
    LEFT JOIN income_band ib ON ib.ib_income_band_sk = hd.hd_income_band_sk
    LEFT JOIN web_sales ws ON c.c_customer_sk = ws.ws_bill_customer_sk
    LEFT JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk
    WHERE cd.cd_gender = 'M'
    GROUP BY c.c_customer_sk, c.c_first_name, c.c_last_name, d.d_date
),
StoreDetails AS (
    SELECT 
        s_store_sk, 
        s_store_name, 
        CONCAT(s_city, ', ', s_state) AS store_location 
    FROM store 
    WHERE s_state = 'CA'
),
FinalResult AS (
    SELECT 
        cd.full_name, 
        ad.full_address, 
        sd.s_store_name AS store_name, 
        sd.store_location, 
        cd.last_purchase_date, 
        cd.income_potential
    FROM CustomerDetails cd
    JOIN AddressDetails ad ON ad.ca_address_sk = cd.c_customer_sk
    JOIN StoreDetails sd ON sd.s_store_sk = cd.c_customer_sk
)
SELECT 
    full_name, 
    full_address, 
    store_name, 
    store_location,
    last_purchase_date,
    income_potential
FROM FinalResult;
