SELECT *
FROM store_sales
    LEFT OUTER JOIN item ON ss_item_sk = i_item_sk
    RIGHT OUTER JOIN store ON ss_store_sk = s_store_sk
    FULL OUTER JOIN promotion ON ss_promo_sk = p_promo_sk
    LEFT OUTER JOIN customer ON ss_customer_sk = c_customer_sk
    RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    FULL OUTER JOIN customer_demographics ON c_current_cdemo_sk = cd_demo_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
WHERE cs_quantity > 100;
