SELECT ss_item_sk, ss_net_profit, cd_gender, hd_demo_sk, ca_state
FROM store_sales
    LEFT OUTER JOIN customer               ON ss_customer_sk = c_customer_sk
    LEFT OUTER JOIN customer_demographics  ON c_current_cdemo_sk = cd_demo_sk
    LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk
    LEFT OUTER JOIN customer_address       ON c_current_addr_sk = ca_address_sk
WHERE ss_net_profit > 0;
