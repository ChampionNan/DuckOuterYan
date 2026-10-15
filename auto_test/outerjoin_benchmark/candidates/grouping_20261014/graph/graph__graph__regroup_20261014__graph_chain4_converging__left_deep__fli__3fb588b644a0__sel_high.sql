-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__graph_chain4_converging__left_deep__lfi__b6911314__inputcap1__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.dst, R3.dst, R4.dst
FROM (((R1 R1 FULL OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 40) R2 ON R1.dst = R2.dst) LEFT OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 40) R3 ON R2.dst = R3.dst) INNER JOIN (SELECT src, dst FROM R4 WHERE src <= 40) R4 ON R3.dst = R4.dst)
WHERE R1.src <= 306;
