SELECT *
FROM (( web_sales LEFT OUTER JOIN item ON ws_item_sk = i_item_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk) ON ws_bill_customer_sk = c_customer_sk)
WHERE i_wholesale_cost IN (1, 5, 10, 50, 100, 500);
