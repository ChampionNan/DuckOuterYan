SELECT *
FROM store_sales
    FULL OUTER JOIN item ON ss_item_sk = i_item_sk
    LEFT OUTER JOIN store ON ss_store_sk = s_store_sk
    RIGHT OUTER JOIN promotion ON ss_promo_sk = p_promo_sk
    FULL OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    RIGHT OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE d_month_seq BETWEEN 50 AND 5000;
