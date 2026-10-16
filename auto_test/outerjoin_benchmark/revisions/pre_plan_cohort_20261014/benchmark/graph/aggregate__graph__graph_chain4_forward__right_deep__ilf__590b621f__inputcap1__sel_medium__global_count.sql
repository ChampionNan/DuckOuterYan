-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((SELECT src, dst FROM R4 WHERE src <= 20) R4 INNER JOIN ((SELECT src, dst FROM R3 WHERE src <= 20) R3 LEFT OUTER JOIN ((SELECT src, dst FROM R2 WHERE src <= 20) R2 FULL OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R3.dst = R4.src)
WHERE R1.src <= 83;
