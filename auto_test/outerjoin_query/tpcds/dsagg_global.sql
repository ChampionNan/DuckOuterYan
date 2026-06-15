SELECT COUNT(*) AS cnt, SUM(ss_net_profit) AS profit FROM ((store_sales LEFT OUTER JOIN item ON ss_item_sk=i_item_sk) LEFT OUTER JOIN store ON ss_store_sk=s_store_sk);
