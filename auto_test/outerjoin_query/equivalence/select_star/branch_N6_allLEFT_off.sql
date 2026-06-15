SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) LEFT OUTER JOIN (R3 LEFT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src) LEFT OUTER JOIN (R5 LEFT OUTER JOIN R6 ON R5.dst=R6.src) ON R2.dst=R5.src);
