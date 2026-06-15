SET disabled_optimizers TO 'outer_yan';
SELECT * FROM ((R1 RIGHT OUTER JOIN R2 ON R1.dst=R2.src) RIGHT OUTER JOIN (R3 RIGHT OUTER JOIN R4 ON R3.dst=R4.src) ON R2.dst=R3.src);
