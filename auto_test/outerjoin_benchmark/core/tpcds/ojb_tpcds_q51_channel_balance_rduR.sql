-- source: TPC-DS Q51
-- transformation: connected join-subgraph adaptation; uniform right-deep RIGHT OUTER JOIN control
-- business_semantics: Web and store sales streams are reconciled by item and date coverage.
SELECT *
FROM (store_sales ss RIGHT OUTER JOIN (date_dim d RIGHT OUTER JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk) ON ws.ws_item_sk = ss.ss_item_sk AND ws.ws_sold_date_sk = ss.ss_sold_date_sk)
WHERE ws.ws_order_number % 1000 = 0;
