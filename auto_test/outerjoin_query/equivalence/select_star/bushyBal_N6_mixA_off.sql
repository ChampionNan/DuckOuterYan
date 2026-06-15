SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) INNER JOIN R3 ON R2.dst=R3.src) RIGHT OUTER JOIN ((R4 FULL OUTER JOIN R5 ON R4.dst=R5.src) LEFT OUTER JOIN R6 ON R5.dst=R6.src) ON R3.dst=R4.src);
