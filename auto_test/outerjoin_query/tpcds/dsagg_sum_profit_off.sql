SET disabled_optimizers TO 'outer_yan';
SELECT ca_state, SUM(ss_net_profit) AS profit FROM ((store_sales FULL OUTER JOIN customer ON ss_customer_sk=c_customer_sk) FULL OUTER JOIN customer_address ON c_current_addr_sk=ca_address_sk) GROUP BY ca_state;
