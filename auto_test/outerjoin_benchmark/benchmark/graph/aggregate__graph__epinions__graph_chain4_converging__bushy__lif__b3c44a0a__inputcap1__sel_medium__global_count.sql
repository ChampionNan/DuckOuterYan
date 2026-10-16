-- graph_dataset: epinions; replaces Bitcoin instance: aggregate__graph__graph_chain4_converging__bushy__lif__b3c44a0a__inputcap1__sel_medium__global_count
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph chain/4/converging
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT COUNT(*) AS row_count
FROM ((R1 R1 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 824) R2 ON R1.dst = R2.dst) INNER JOIN ((SELECT src, dst FROM R4 WHERE src <= 824) R4 FULL OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 824) R3 ON R3.dst = R4.dst) ON R2.dst = R3.dst)
WHERE R1.src <= 2177;
