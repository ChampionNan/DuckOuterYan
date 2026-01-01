SELECT R.src as v1, R.dst as v2, S.src as v3, S.dst as v4, T.src as v5, T.dst as v6, K.src as v7, K.dst as v8
FROM R LEFT OUTER JOIN S ON R.dst = S.src
LEFT OUTER JOIN T ON S.dst = T.src
FULL OUTER JOIN K ON T.dst = K.src;