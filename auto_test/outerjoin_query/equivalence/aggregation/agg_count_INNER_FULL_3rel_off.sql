SET disabled_optimizers TO 'outer_yan';
SELECT R.src AS v1, COUNT(*) AS cnt FROM R INNER JOIN S ON R.dst=S.src FULL OUTER JOIN T ON S.dst=T.src GROUP BY R.src;
