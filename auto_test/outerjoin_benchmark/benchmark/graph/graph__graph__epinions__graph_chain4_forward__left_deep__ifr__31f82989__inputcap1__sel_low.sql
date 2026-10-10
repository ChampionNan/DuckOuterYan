-- graph_dataset: epinions; replaces Bitcoin instance: graph__graph__graph_chain4_forward__left_deep__ifr__31f82989__inputcap1__sel_low
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/forward
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM ((((SELECT src, dst FROM R2 WHERE src <= 539) R2 INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 539) R3 ON R2.dst = R3.src) FULL OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 539) R4 ON R3.dst = R4.src) RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.src)
WHERE R1.src <= 118;
