-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph branch/6/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((((R2 R2 LEFT OUTER JOIN R4 R4 ON R2.dst = R4.dst) FULL OUTER JOIN R3 R3 ON R2.dst = R3.dst) INNER JOIN R6 R6 ON R3.dst = R6.dst) RIGHT OUTER JOIN R5 R5 ON R3.dst = R5.dst) INNER JOIN R1 R1 ON R1.dst = R2.dst)
WHERE R1.src <= 306;
