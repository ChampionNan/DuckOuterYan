SELECT *
FROM (( web_sales LEFT OUTER JOIN item ON ws_item_sk = i_item_sk) INNER JOIN ( customer RIGHT OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ws_bill_customer_sk = c_customer_sk)
WHERE ca_address_sk > 500;
