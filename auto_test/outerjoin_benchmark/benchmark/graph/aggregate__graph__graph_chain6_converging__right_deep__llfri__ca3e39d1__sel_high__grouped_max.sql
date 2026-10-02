-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/6/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst AS group_key, MAX(R5.dst) AS max_key
FROM (R1 R1 LEFT OUTER JOIN (R6 R6 LEFT OUTER JOIN (R5 R5 FULL OUTER JOIN (R4 R4 RIGHT OUTER JOIN (R3 R3 INNER JOIN R2 R2 ON R2.dst = R3.dst) ON R3.dst = R4.dst) ON R4.dst = R5.dst) ON R5.dst = R6.dst) ON R1.dst = R2.dst)
WHERE R1.src <= 306
GROUP BY R1.dst;
