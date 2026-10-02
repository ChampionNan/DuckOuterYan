-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst AS group_key, SUM(R3.dst) AS key_sum
FROM ((R1 R1 LEFT OUTER JOIN R2 R2 ON R1.dst = R2.dst) INNER JOIN (R4 R4 FULL OUTER JOIN R3 R3 ON R3.dst = R4.dst) ON R2.dst = R3.dst)
WHERE R1.src <= 2
GROUP BY R1.dst;
