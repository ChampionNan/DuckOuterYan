SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (R1 LEFT OUTER JOIN (R2 INNER JOIN (R3 RIGHT OUTER JOIN (R4 FULL OUTER JOIN R5 ON R4.dst=R5.src) ON R3.dst=R4.src) ON R2.dst=R3.src) ON R1.dst=R2.src);
