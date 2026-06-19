WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY count(ca.id) DESC) AS rank
    FROM title t
    JOIN movie_keyword mk ON mk.movie_id = t.id
    JOIN keyword k ON k.id = mk.keyword_id
    LEFT JOIN complete_cast cc ON cc.movie_id = t.id
    LEFT JOIN cast_info ca ON ca.movie_id = t.id
    GROUP BY t.id, t.title, t.production_year
),
TopMovies AS (
    SELECT 
        movie_id,
        title,
        production_year
    FROM RankedMovies
    WHERE rank <= 10
)
SELECT 
    tm.title,
    tm.production_year,
    cn.name AS company_name,
    rt.role,
    pi.info AS person_info
FROM TopMovies tm
JOIN complete_cast cc ON cc.movie_id = tm.movie_id
JOIN cast_info ci ON ci.id = cc.subject_id
JOIN role_type rt ON rt.id = ci.role_id
JOIN movie_companies mc ON mc.movie_id = tm.movie_id
JOIN company_name cn ON cn.id = mc.company_id
LEFT JOIN person_info pi ON pi.person_id = ci.person_id;
