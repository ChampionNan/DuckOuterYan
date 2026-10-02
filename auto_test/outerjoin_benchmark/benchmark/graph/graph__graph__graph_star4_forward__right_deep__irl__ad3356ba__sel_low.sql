-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R3.src, R4.src
FROM (R4 R4 INNER JOIN (R3 R3 RIGHT OUTER JOIN (R2 R2 LEFT OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R1.dst = R3.src) ON R1.dst = R4.src)
WHERE R1.src <= 2;
