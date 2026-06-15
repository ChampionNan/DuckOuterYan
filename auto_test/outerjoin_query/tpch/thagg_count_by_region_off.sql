SET disabled_optimizers TO 'outer_yan';
SELECT r_name, COUNT(*) AS cnt FROM (((region FULL OUTER JOIN nation ON r_regionkey=n_regionkey) FULL OUTER JOIN supplier ON n_nationkey=s_nationkey) FULL OUTER JOIN customer ON s_nationkey=c_nationkey) GROUP BY r_name;
