SELECT *
FROM (( web_sales LEFT OUTER JOIN customer ON ws_bill_customer_sk = c_customer_sk) RIGHT OUTER JOIN ( item FULL OUTER JOIN date_dim ON 1=1) ON ws_item_sk = i_item_sk)
WHERE p_promo_sk < 50000;
