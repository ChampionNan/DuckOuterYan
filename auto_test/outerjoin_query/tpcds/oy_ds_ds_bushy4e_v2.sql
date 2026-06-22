SELECT *
FROM (( web_sales FULL OUTER JOIN item ON ws_item_sk = i_item_sk) LEFT OUTER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ws_bill_customer_sk = c_customer_sk)
WHERE c_customer_sk BETWEEN 1 AND 100;
