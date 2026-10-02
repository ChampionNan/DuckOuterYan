-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.dst AS group_key, MAX(R1.dst) AS max_key
FROM ((((SELECT src, dst FROM R2 WHERE src <= 10) R2 RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.dst) FULL OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 10) R4 ON R1.dst = R4.dst) LEFT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 10) R3 ON R1.dst = R3.dst)
WHERE R1.src <= 2
GROUP BY R2.dst;
