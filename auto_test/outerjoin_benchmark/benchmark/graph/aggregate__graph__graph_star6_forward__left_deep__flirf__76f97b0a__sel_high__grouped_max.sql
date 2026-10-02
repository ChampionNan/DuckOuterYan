-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/6/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.src AS group_key, MAX(R1.dst) AS max_key
FROM (((((R1 R1 FULL OUTER JOIN R2 R2 ON R1.dst = R2.src) LEFT OUTER JOIN R3 R3 ON R1.dst = R3.src) INNER JOIN R4 R4 ON R1.dst = R4.src) RIGHT OUTER JOIN R5 R5 ON R1.dst = R5.src) FULL OUTER JOIN R6 R6 ON R1.dst = R6.src)
WHERE R1.src <= 306
GROUP BY R2.src;
