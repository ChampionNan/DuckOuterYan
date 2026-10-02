-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst AS group_key, SUM(R4.src) AS key_sum
FROM (R5 R5 INNER JOIN (R4 R4 FULL OUTER JOIN (R3 R3 LEFT OUTER JOIN (R2 R2 RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R3.dst = R4.src) ON R4.dst = R5.src)
WHERE R1.src <= 306
GROUP BY R1.dst;
