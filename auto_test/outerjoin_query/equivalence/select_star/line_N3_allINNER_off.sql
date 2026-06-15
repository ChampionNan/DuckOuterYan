SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((R1 INNER JOIN R2 ON R1.dst=R2.src) INNER JOIN R3 ON R2.dst=R3.src);
