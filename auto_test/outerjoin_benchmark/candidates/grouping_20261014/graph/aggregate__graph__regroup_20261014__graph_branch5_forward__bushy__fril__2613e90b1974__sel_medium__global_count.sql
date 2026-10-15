-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__graph__graph_branch5_forward__bushy__rlfi__361c9871__inputcap1__sel_medium__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM (((SELECT src, dst FROM R5 WHERE src <= 20) R5 FULL OUTER JOIN (SELECT src, dst FROM R3 WHERE src <= 20) R3 ON R3.dst = R5.src) RIGHT OUTER JOIN (R1 R1 INNER JOIN ((SELECT src, dst FROM R4 WHERE src <= 20) R4 LEFT OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 20) R2 ON R2.dst = R4.src) ON R1.dst = R2.src) ON R2.dst = R3.src)
WHERE R1.src <= 83;
