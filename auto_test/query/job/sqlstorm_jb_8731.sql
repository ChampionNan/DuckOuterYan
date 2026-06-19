
WITH RankedMovies AS (
    SELECT t.id AS movie_id, t.title, t.production_year, COUNT(DISTINCT k.id) AS keyword_count
    FROM title t
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    WHERE t.production_year > 2000
    GROUP BY t.id, t.title, t.production_year
),
TopMovies AS (
    SELECT movie_id, title, production_year, keyword_count,
           RANK() OVER (ORDER BY keyword_count DESC) AS rank
    FROM RankedMovies
    WHERE keyword_count > 5
)
SELECT tm.title, tm.production_year, an.name AS director_name, ci.role_id
FROM TopMovies tm
JOIN complete_cast cc ON tm.movie_id = cc.movie_id
JOIN cast_info ci ON cc.subject_id = ci.id
JOIN aka_name an ON ci.person_id = an.person_id
JOIN person_info pi ON ci.person_id = pi.person_id
JOIN role_type rt ON ci.role_id = rt.id
WHERE rt.role = 'director' AND pi.info_type_id = (SELECT id FROM info_type WHERE info = 'biography')
  AND tm.rank <= 10;
