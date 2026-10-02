-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/converging
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM (R4 R4 LEFT OUTER JOIN (R3 R3 RIGHT OUTER JOIN (R2 R2 INNER JOIN R1 R1 ON R1.dst = R2.dst) ON R1.dst = R3.dst) ON R1.dst = R4.dst)
WHERE R1.src <= 83;
