-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst AS group_key, SUM(R3.src) AS key_sum
FROM ((SELECT src, dst FROM R4 WHERE src <= 40) R4 FULL OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 40) R3 RIGHT OUTER JOIN ((SELECT src, dst FROM R2 WHERE src <= 40) R2 INNER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R3.dst = R4.src)
WHERE R1.src <= 306
GROUP BY R1.dst;
