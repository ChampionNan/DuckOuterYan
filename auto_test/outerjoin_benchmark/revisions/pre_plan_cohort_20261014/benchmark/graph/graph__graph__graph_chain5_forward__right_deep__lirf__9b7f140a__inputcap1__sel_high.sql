-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src, R4.dst, R5.src
FROM (R1 R1 LEFT OUTER JOIN ((SELECT src, dst FROM R5 WHERE src <= 40) R5 INNER JOIN ((SELECT src, dst FROM R4 WHERE src <= 40) R4 RIGHT OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 40) R3 FULL OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R2.dst = R3.src) ON R3.dst = R4.src) ON R4.dst = R5.src) ON R1.dst = R2.src)
WHERE R1.src <= 306;
