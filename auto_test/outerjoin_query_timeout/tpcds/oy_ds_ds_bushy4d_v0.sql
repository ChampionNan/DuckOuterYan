SELECT *
FROM (( store_sales LEFT OUTER JOIN item ON ss_item_sk = i_item_sk) RIGHT OUTER JOIN ( customer FULL OUTER JOIN date_dim ON 1=1) ON ss_customer_sk = c_customer_sk)
WHERE ss_net_profit < 200;
