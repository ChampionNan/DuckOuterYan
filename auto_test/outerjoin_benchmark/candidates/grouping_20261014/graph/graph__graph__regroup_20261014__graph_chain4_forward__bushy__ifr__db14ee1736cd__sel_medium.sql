-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: graph__graph__graph_chain4_forward__bushy__rfi__4c9cda91__inputcap1__sel_medium
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst, R2.src, R2.dst, R3.src, R3.dst, R4.src
FROM (((SELECT src, dst FROM R4 WHERE src <= 20) R4 INNER JOIN (SELECT src, dst FROM R3 WHERE src <= 20) R3 ON R3.dst = R4.src) FULL OUTER JOIN (R1 R1 RIGHT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 20) R2 ON R1.dst = R2.src) ON R2.dst = R3.src)
WHERE R1.src <= 83;
