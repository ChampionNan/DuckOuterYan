SELECT *
FROM store_sales
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
    LEFT OUTER JOIN income_band ON hd_income_band_sk = ib_income_band_sk
WHERE ss_sales_price BETWEEN 1 AND 100;
