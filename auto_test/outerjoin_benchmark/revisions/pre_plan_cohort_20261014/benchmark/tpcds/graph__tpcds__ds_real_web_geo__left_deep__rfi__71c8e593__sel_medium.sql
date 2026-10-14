-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpcds__ds_real_web_geo__rfi__sel_high
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT ws_item_sk, ws_sales_price, c_last_name, ca_state, d_year
FROM web_sales
    RIGHT OUTER JOIN customer         ON ws_bill_customer_sk = c_customer_sk
    FULL OUTER JOIN customer_address ON c_current_addr_sk = ca_address_sk
    INNER JOIN date_dim         ON ws_sold_date_sk = d_date_sk
WHERE web_sales.ws_quantity <= 30;