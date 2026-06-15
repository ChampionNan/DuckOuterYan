SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((R1 FULL OUTER JOIN R2 ON R1.dst=R2.src) FULL OUTER JOIN (R3 FULL OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src);
