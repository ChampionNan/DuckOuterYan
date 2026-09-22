-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFI; relation and predicate structure unchanged
SELECT ws_item_sk, ws_sales_price, c_last_name, ca_state, d_year
FROM web_sales
    RIGHT OUTER JOIN customer         ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN date_dim         ON ws_sold_date_sk = d_date_sk
WHERE ws_quantity > 0;
