SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((R1 LEFT OUTER JOIN (R2 LEFT OUTER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src) LEFT OUTER JOIN (R4 LEFT OUTER JOIN (R5 LEFT OUTER JOIN R6 ON R5.dst=R6.src) ON R4.dst=R5.src) ON R3.dst=R4.src);
