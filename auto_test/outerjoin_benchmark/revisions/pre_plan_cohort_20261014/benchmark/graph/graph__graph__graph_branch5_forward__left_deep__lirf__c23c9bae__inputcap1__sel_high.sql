-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/5/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R4.src, R3.dst, R5.src
FROM ((((R1 R1 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst = R2.src) INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R2.dst = R3.src) RIGHT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 40) R4 ON R2.dst = R4.src) FULL OUTER JOIN (SELECT src, dst FROM R5 WHERE src <= 40) R5 ON R3.dst = R5.src)
WHERE R1.src <= 306;
