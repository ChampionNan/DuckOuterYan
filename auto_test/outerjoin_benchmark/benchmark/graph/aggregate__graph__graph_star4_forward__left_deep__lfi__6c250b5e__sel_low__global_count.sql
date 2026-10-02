-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM (((R1 R1 LEFT OUTER JOIN R2 R2 ON R1.dst = R2.src) FULL OUTER JOIN R3 R3 ON R1.dst = R3.src) INNER JOIN R4 R4 ON R1.dst = R4.src)
WHERE R1.src <= 2;
