SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((((R1 FULL OUTER JOIN R2 ON R1.dst=R2.src) RIGHT OUTER JOIN R3 ON R1.dst=R3.src) INNER JOIN R4 ON R1.dst=R4.src) LEFT OUTER JOIN R5 ON R1.dst=R5.src);
