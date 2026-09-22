-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILR; relation and predicate structure unchanged
SELECT *
FROM title t
    INNER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN aka_name an ON n.id = an.person_id
WHERE an.person_id % 7 <> 0;
