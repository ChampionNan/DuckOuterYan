SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) INNER JOIN R3 ON R1.dst=R3.src) RIGHT OUTER JOIN R4 ON R1.dst=R4.src) WHERE R2.src >= 100;
