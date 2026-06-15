SET disabled_optimizers TO 'outer_yan';
SELECT i_category, COUNT(*) AS cnt FROM ((store_sales FULL OUTER JOIN item ON ss_item_sk=i_item_sk) FULL OUTER JOIN store ON ss_store_sk=s_store_sk) GROUP BY i_category;
