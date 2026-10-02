-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/5/forward
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.src AS group_key, SUM(R1.dst) AS key_sum
FROM ((((R2 R2 RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.src) LEFT OUTER JOIN R5 R5 ON R1.dst = R5.src) INNER JOIN R4 R4 ON R1.dst = R4.src) FULL OUTER JOIN R3 R3 ON R1.dst = R3.src)
WHERE R1.src <= 83
GROUP BY R2.src;
