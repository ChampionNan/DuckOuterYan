SELECT S.src, min(K.dst) as total
FROM R INNER JOIN S ON R.dst = S.src
INNER JOIN T ON S.dst = T.src
RIGHT OUTER JOIN K ON T.dst = K.src
GROUP BY S.src;