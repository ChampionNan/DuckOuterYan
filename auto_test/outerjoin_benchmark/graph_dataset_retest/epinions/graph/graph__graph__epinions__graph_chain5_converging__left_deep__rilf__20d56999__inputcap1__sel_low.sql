-- graph_dataset: epinions; replaces Bitcoin instance: graph__graph__graph_chain5_converging__left_deep__rilf__20d56999__inputcap1__sel_low
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst
FROM ((((R1 R1 RIGHT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 539) R2 ON R1.dst = R2.dst) INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 539) R3 ON R2.dst = R3.dst) LEFT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 539) R4 ON R3.dst = R4.dst) FULL OUTER JOIN (SELECT src, dst FROM R5 WHERE src <= 539) R5 ON R4.dst = R5.dst)
WHERE R1.src <= 118;
