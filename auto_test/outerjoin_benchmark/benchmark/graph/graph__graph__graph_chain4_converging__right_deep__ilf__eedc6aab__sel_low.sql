-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM (R1 R1 INNER JOIN (R4 R4 LEFT OUTER JOIN (R3 R3 FULL OUTER JOIN R2 R2 ON R2.dst = R3.dst) ON R3.dst = R4.dst) ON R1.dst = R2.dst)
WHERE R1.src <= 2;
