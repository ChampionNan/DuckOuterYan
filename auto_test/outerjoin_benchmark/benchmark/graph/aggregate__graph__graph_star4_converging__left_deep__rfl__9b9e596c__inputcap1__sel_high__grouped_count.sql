-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__graph__graph_star4_converging__left_deep__rfl__9b9e596c__inputcap1__sel_high__grouped_max; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Synthetic Graph star/4/converging
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT R2.dst AS group_key, COUNT(*) AS row_count
FROM ((((SELECT src, dst FROM R2 WHERE src <= 40) R2 RIGHT OUTER JOIN R1 R1 ON R1.dst = R2.dst) FULL OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 40) R4 ON R1.dst = R4.dst) LEFT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R1.dst = R3.dst)
WHERE R1.src <= 306
GROUP BY R2.dst;
