-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__graph_chain4_forward__left_deep__lir__5592c5b1__inputcap1__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM (((R1 R1 RIGHT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 10) R2 ON R1.dst = R2.src) INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 10) R3 ON R2.dst = R3.src) LEFT OUTER JOIN (SELECT src, dst FROM R4 WHERE src <= 10) R4 ON R3.dst = R4.src)
WHERE R1.src <= 2;
