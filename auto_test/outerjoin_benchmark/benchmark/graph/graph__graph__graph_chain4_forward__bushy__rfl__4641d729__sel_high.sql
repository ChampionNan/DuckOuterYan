-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM ((R1 R1 RIGHT OUTER JOIN R2 R2 ON R1.dst = R2.src) FULL OUTER JOIN (R4 R4 LEFT OUTER JOIN R3 R3 ON R3.dst = R4.src) ON R2.dst = R3.src)
WHERE R1.src <= 306;
