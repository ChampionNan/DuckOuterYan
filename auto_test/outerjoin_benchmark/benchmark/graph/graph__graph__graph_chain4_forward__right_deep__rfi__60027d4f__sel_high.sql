-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM (R4 R4 RIGHT OUTER JOIN (R3 R3 FULL OUTER JOIN (R2 R2 INNER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R3.dst = R4.src)
WHERE R1.src <= 306;
