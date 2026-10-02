-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/5/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.dst AS group_key, MAX(R1.dst) AS max_key
FROM (R5 R5 LEFT OUTER JOIN (R4 R4 FULL OUTER JOIN (R3 R3 INNER JOIN (R2 R2 RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.dst) ON R1.dst = R3.dst) ON R1.dst = R4.dst) ON R1.dst = R5.dst)
WHERE R1.src <= 306
GROUP BY R2.dst;
