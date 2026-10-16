-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/5/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((SELECT src, dst FROM R5 WHERE src <= 40) R5 RIGHT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R3.dst = R5.src) LEFT OUTER JOIN (R1 R1 FULL OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 40) R4 INNER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R2.dst = R4.src) ON R1.dst = R2.src) ON R2.dst = R3.src)
WHERE R1.src <= 306;
