SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((R1 LEFT OUTER JOIN R2 ON R1.dst=R2.src) LEFT OUTER JOIN R3 ON R2.dst=R3.src) WHERE R1.dst BETWEEN 0 AND 1000000;
