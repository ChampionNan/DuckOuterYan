SELECT R.src as v1, R.dst as v2, S.src as v3, S.dst as v4, T.src as v5, T.dst as v6 FROM R 
RIGHT OUTER JOIN S ON R.dst = S.src 
FULL OUTER JOIN T ON S.dst = T.src;