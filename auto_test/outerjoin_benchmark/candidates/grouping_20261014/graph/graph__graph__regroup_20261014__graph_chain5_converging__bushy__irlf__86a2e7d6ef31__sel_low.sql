-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__epinions__graph_chain5_converging__bushy__rfli__0b18afaa__inputcap1__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.dst, R3.dst, R4.dst, R5.dst
FROM ((R1 R1 INNER JOIN (SELECT src, dst FROM R2 WHERE src <= 539) R2 ON R1.dst = R2.dst) RIGHT OUTER JOIN ((SELECT src, dst FROM R5 WHERE src <= 539) R5 LEFT OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 539) R4 FULL OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 539) R3 ON R3.dst = R4.dst) ON R4.dst = R5.dst) ON R2.dst = R3.dst)
WHERE R1.src <= 118;
