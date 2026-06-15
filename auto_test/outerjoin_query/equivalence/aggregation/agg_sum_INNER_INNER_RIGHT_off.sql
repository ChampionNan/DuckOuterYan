SET disabled_optimizers TO 'outer_yan';
SELECT R.src AS v1, sum(K.dst) AS total FROM R INNER JOIN S ON R.dst=S.src INNER JOIN T ON S.dst=T.src RIGHT OUTER JOIN K ON T.dst=K.src GROUP BY R.src;
