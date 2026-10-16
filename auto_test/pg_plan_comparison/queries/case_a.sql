-- Derived from JOB 3c: title, movie_info, movie_keyword and their original edges.
-- Keep titles with no matching info/keyword pair. Drop the keyword dimension
-- and MIN/text predicates; use a fixed 0.1% title-key filter for bounded output.
SELECT t.id AS title_id, mi.id AS info_id,
       mk.id AS keyword_row_id, mk.keyword_id
FROM title t LEFT JOIN
     (movie_info mi INNER JOIN movie_keyword mk ON mi.movie_id = mk.movie_id)
     ON t.id = mi.movie_id
WHERE t.id % 1000 = 0;
