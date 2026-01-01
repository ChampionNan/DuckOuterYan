SELECT S.src, max(K.dst) as total
FROM R INNER JOIN S ON R.dst = S.src
INNER JOIN T ON S.dst = T.src
FULL OUTER JOIN K ON T.dst = K.src
GROUP BY S.src;