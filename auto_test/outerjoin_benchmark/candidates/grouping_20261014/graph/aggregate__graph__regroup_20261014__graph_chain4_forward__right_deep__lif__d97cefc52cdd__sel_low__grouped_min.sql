-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__graph__graph_chain4_forward__right_deep__ifl__abd23719__inputcap1__sel_low__grouped_min
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT R1.dst AS group_key, MIN(R3.src) AS min_key
FROM (R1 R1 LEFT OUTER JOIN ((SELECT src, dst FROM R4 WHERE src <= 10) R4 INNER JOIN ((SELECT src, dst FROM R3 WHERE src <= 10) R3 FULL OUTER JOIN (SELECT src, dst FROM R2 WHERE src <= 10) R2 ON R2.dst = R3.src) ON R3.dst = R4.src) ON R1.dst = R2.src)
WHERE R1.src <= 2
GROUP BY R1.dst;
