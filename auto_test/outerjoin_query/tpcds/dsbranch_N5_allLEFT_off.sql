SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((store_sales LEFT OUTER JOIN item ON ss_item_sk=i_item_sk) LEFT OUTER JOIN ((customer LEFT OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk) LEFT OUTER JOIN customer_demographics ON c_current_cdemo_sk=cd_demo_sk) ON ss_customer_sk=c_customer_sk);
