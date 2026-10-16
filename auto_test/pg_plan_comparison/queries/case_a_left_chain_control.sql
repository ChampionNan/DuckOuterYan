-- Positive control: LEFT-(LEFT) satisfies PG's strict identity-3 rule.
-- This changes Case A semantics; it is only an enumeration control.
SELECT t.id AS title_id, mi.id AS info_id,
       mk.id AS keyword_row_id, mk.keyword_id
FROM title t LEFT JOIN
     (movie_info mi LEFT JOIN movie_keyword mk ON mi.movie_id = mk.movie_id)
     ON t.id = mi.movie_id
WHERE t.id % 1000 = 0;
