SET disabled_optimizers TO 'outer_yan';
SELECT * FROM store_sales RIGHT OUTER JOIN item ON ss_item_sk=i_item_sk;
