SELECT *
FROM web_sales RIGHT OUTER JOIN (customer INNER JOIN (customer_address FULL OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk) ON c_current_addr_sk = ca_address_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE s_number_employees >= 10;
