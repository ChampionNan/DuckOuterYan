SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (R1 FULL OUTER JOIN (R2 FULL OUTER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src);
