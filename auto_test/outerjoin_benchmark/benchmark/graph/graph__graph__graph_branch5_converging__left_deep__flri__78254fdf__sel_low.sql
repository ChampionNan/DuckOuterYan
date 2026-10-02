-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/5/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst
FROM ((((R2 R2 FULL OUTER JOIN R4 R4 ON R2.dst = R4.dst) LEFT OUTER JOIN R3 R3 ON R2.dst = R3.dst) RIGHT OUTER JOIN R5 R5 ON R3.dst = R5.dst) INNER JOIN R1 R1 ON R1.dst = R2.dst)
WHERE R1.src <= 2;
