SELECT *
FROM store_sales
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
    RIGHT OUTER JOIN income_band ON hd_income_band_sk = ib_income_band_sk
WHERE ss_quantity % 7 <> 0;
