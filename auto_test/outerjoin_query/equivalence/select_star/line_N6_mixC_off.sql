SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((((R1 RIGHT OUTER JOIN R2 ON R1.dst=R2.src) FULL OUTER JOIN R3 ON R2.dst=R3.src) LEFT OUTER JOIN R4 ON R3.dst=R4.src) INNER JOIN R5 ON R4.dst=R5.src) RIGHT OUTER JOIN R6 ON R5.dst=R6.src);
