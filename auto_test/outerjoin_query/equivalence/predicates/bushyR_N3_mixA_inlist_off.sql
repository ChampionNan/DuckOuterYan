SET disabled_optimizers TO 'outer_yan';
SELECT * FROM (R1 LEFT OUTER JOIN (R2 INNER JOIN R3 ON R2.dst=R3.src) ON R1.dst=R2.src) WHERE R1.src IN (10, 210, 410, 610, 810);
