-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/5/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R3.src, R4.src, R5.src
FROM (((((SELECT src, dst FROM R2 WHERE src <= 10) R2 FULL OUTER JOIN R1 R1 ON R1.dst = R2.src) RIGHT OUTER JOIN (SELECT src, dst FROM R5 WHERE src <= 10) R5 ON R1.dst = R5.src) LEFT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 10) R4 ON R1.dst = R4.src) INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 10) R3 ON R1.dst = R3.src)
WHERE R1.src <= 2;
