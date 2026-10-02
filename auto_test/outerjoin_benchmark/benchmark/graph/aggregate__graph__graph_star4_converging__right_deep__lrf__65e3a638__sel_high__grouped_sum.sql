-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.dst AS group_key, SUM(R1.dst) AS key_sum
FROM (R3 R3 LEFT OUTER JOIN (R4 R4 RIGHT OUTER JOIN (R1 R1 FULL OUTER JOIN R2 R2 ON R1.dst = R2.dst) ON R1.dst = R4.dst) ON R1.dst = R3.dst)
WHERE R1.src <= 306
GROUP BY R2.dst;
