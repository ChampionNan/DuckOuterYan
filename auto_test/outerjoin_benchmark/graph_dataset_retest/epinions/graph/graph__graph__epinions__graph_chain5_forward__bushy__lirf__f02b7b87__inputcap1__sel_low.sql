-- graph_dataset: epinions; replaces Bitcoin instance: graph__graph__graph_chain5_forward__bushy__lirf__f02b7b87__inputcap1__sel_low
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/5/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src, R4.dst, R5.src
FROM ((R1 R1 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 539) R2 ON R1.dst = R2.src) INNER JOIN ((SELECT src, dst FROM R5 WHERE src <= 539) R5 RIGHT OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 539) R4 FULL OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 539) R3 ON R3.dst = R4.src) ON R4.dst = R5.src) ON R2.dst = R3.src)
WHERE R1.src <= 118;
