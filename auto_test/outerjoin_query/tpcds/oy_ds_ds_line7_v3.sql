SELECT *
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    INNER JOIN store ON ss_store_sk = s_store_sk
    RIGHT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    INNER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE cs_sales_price < 50000;
