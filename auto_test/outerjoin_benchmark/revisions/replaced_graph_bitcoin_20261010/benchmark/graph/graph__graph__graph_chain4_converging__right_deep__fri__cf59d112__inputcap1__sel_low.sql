-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM ((SELECT src, dst FROM R4 WHERE src <= 10) R4 FULL OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 10) R3 RIGHT OUTER JOIN ((SELECT src, dst FROM R2 WHERE src <= 10) R2 INNER JOIN R1 R1 ON R1.dst = R2.dst) ON R2.dst = R3.dst) ON R3.dst = R4.dst)
WHERE R1.src <= 2;
