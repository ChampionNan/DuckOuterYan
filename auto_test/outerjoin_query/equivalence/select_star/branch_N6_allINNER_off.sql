SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((R1 INNER JOIN R2 ON R1.dst=R2.src) INNER JOIN (R3 INNER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) INNER JOIN (R5 INNER JOIN R6 ON R5.dst=R6.src) ON R2.dst=R5.src);
