-- Connected four-relation subgraph of SQLStorm TPC-DS 14368.
-- Original equality edges; one fact table; adapted mixed join kinds/grouping.
SELECT *
FROM customer_address ca RIGHT OUTER JOIN
    (customer c LEFT OUTER JOIN
        (web_sales ws INNER JOIN item i ON ws.ws_item_sk = i.i_item_sk)
        ON c.c_customer_sk = ws.ws_bill_customer_sk)
    ON c.c_current_addr_sk = ca.ca_address_sk
WHERE (c.c_customer_sk % 100) < 3;
