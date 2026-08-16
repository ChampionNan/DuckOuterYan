SELECT *
FROM (( web_sales RIGHT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk) FULL OUTER JOIN ( item LEFT OUTER JOIN date_dim ON 1=1) ON ws_item_sk = i_item_sk)
WHERE c_customer_sk % 7 <> 0;
