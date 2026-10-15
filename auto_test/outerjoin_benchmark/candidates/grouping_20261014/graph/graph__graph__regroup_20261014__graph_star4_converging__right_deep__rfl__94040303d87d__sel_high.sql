-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__graph_star4_converging__right_deep__lrf__65e3a638__inputcap1__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM ((SELECT src, dst FROM R3 WHERE src <= 40) R3 RIGHT OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 40) R4 FULL OUTER JOIN (R1 R1 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst = R2.dst) ON R1.dst = R4.dst) ON R1.dst = R3.dst)
WHERE R1.src <= 306;
