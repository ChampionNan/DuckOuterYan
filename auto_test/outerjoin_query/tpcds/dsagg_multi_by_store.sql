SELECT s_state, COUNT(*) AS cnt, SUM(ss_quantity) AS qty FROM ((store_sales FULL OUTER JOIN item ON ss_item_sk=i_item_sk) RIGHT OUTER JOIN store ON ss_store_sk=s_store_sk) GROUP BY s_state;
