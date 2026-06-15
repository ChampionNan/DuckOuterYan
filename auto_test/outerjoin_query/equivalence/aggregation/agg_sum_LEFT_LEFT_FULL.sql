SELECT R.src AS v1, sum(K.dst) AS total FROM R LEFT OUTER JOIN S ON R.dst=S.src LEFT OUTER JOIN T ON S.dst=T.src FULL OUTER JOIN K ON T.dst=K.src GROUP BY R.src;
