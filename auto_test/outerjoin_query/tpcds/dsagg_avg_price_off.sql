SET disabled_optimizers TO 'outer_yan';
SELECT ca_state, AVG(ss_sales_price) AS avg_price FROM ((store_sales LEFT OUTER JOIN customer ON ss_customer_sk=c_customer_sk) INNER JOIN customer_address ON c_current_addr_sk=ca_address_sk) GROUP BY ca_state;
