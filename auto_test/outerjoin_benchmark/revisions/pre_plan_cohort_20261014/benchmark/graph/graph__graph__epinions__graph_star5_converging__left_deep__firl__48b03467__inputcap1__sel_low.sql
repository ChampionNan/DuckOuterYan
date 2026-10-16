-- graph_dataset: epinions; replaces Bitcoin instance: graph__graph__graph_star5_converging__left_deep__firl__48b03467__inputcap1__sel_low
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/5/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst
FROM (((((SELECT src, dst FROM R2 WHERE src <= 539) R2 FULL OUTER JOIN R1 R1 ON R1.dst = R2.dst) INNER JOIN (SELECT src, dst FROM R5 WHERE src <= 539) R5 ON R1.dst = R5.dst) RIGHT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 539) R4 ON R1.dst = R4.dst) LEFT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 539) R3 ON R1.dst = R3.dst)
WHERE R1.src <= 118;
