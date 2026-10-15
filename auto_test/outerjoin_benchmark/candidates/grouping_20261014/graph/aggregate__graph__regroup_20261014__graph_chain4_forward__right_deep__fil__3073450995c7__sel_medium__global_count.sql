-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__graph__graph_chain4_forward__right_deep__ilf__590b621f__inputcap1__sel_medium__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM ((SELECT src, dst FROM R4 WHERE src <= 20) R4 FULL OUTER JOIN ((SELECT src, dst FROM R3 WHERE src <= 20) R3 INNER JOIN ((SELECT src, dst FROM R2 WHERE src <= 20) R2 LEFT OUTER JOIN R1 R1 ON R1.dst = R2.src) ON R2.dst = R3.src) ON R3.dst = R4.src)
WHERE R1.src <= 83;
