-- Positive control: changed preservation side, not equivalent to Case A.
-- The title predicate rejects NULL title rows, so PG may reduce RIGHT to INNER.
SELECT t.id AS title_id, mi.id AS info_id,
       mk.id AS keyword_row_id, mk.keyword_id
FROM title t RIGHT JOIN
     (movie_info mi INNER JOIN movie_keyword mk ON mi.movie_id = mk.movie_id)
     ON t.id = mi.movie_id
WHERE t.id % 1000 = 0;
