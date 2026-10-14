-- graph_dataset: epinions; replaces Bitcoin instance: graph__graph__graph_chain4_converging__right_deep__fri__cf59d112__inputcap1__sel_low
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/converging
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM ((SELECT src, dst FROM R4 WHERE src <= 539) R4 FULL OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 539) R3 RIGHT OUTER JOIN ((SELECT src, dst FROM R2 WHERE src <= 539) R2 INNER JOIN R1 R1 ON R1.dst = R2.dst) ON R2.dst = R3.dst) ON R3.dst = R4.dst)
WHERE R1.src <= 118;
