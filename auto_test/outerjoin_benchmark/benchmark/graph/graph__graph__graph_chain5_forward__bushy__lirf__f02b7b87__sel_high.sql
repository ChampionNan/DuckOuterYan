-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src, R4.dst, R5.src
FROM ((R1 R1 LEFT OUTER JOIN R2 R2 ON R1.dst = R2.src) INNER JOIN (R5 R5 RIGHT OUTER JOIN (R4 R4 FULL OUTER JOIN R3 R3 ON R3.dst = R4.src) ON R4.dst = R5.src) ON R2.dst = R3.src)
WHERE R1.src <= 306;
