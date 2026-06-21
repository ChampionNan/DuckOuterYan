SELECT *
FROM web_sales FULL OUTER JOIN (customer INNER JOIN (customer_address LEFT OUTER JOIN household_demographics ON c_current_hdemo_sk = hd_demo_sk) ON c_current_addr_sk = ca_address_sk) ON ws_bill_customer_sk = c_customer_sk
WHERE ss_quantity BETWEEN 50 AND 5000;
