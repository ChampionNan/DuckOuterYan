-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/5/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R4.src, R3.dst, R5.src
FROM (R5 R5 INNER JOIN (R4 R4 FULL OUTER JOIN (R3 R3 RIGHT OUTER JOIN (R2 R2 LEFT OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R2.dst = R4.src) ON R3.dst = R5.src)
WHERE R1.src <= 2;
