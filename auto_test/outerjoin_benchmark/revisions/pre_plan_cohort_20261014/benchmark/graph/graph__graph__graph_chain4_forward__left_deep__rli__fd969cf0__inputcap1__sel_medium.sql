-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM (((R1 R1 RIGHT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 20) R2 ON R1.dst = R2.src) LEFT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 20) R3 ON R2.dst = R3.src) INNER JOIN (SELECT src, dst FROM R4 WHERE src <= 20) R4 ON R3.dst = R4.src)
WHERE R1.src <= 83;
