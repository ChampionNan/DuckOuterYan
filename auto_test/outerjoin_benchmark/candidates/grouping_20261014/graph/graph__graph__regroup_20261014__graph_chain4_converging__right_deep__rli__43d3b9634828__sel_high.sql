-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__graph_chain4_converging__right_deep__irl__6d5efcda__inputcap1__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM ((SELECT src, dst FROM R4 WHERE src <= 40) R4 RIGHT OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 40) R3 LEFT OUTER JOIN ((SELECT src, dst FROM R2 WHERE src <= 40) R2 INNER JOIN R1 R1 ON R1.dst = R2.dst) ON R2.dst = R3.dst) ON R3.dst = R4.dst)
WHERE R1.src <= 306;
