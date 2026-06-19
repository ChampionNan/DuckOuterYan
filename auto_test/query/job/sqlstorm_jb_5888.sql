
WITH MovieData AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.name AS company_name,
        p.name AS person_name,
        r.role AS person_role,
        COUNT(k.keyword) AS keyword_count
    FROM title t
    JOIN complete_cast cc ON t.id = cc.movie_id
    JOIN cast_info ci ON cc.subject_id = ci.id
    JOIN aka_name p ON ci.person_id = p.person_id
    JOIN movie_companies mc ON t.id = mc.movie_id
    JOIN company_name c ON mc.company_id = c.id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    JOIN role_type r ON ci.role_id = r.id
    WHERE t.production_year >= 2000
    GROUP BY t.title, t.production_year, c.name, p.name, r.role
),
RankedMovies AS (
    SELECT 
        movie_title,
        production_year,
        company_name,
        person_name,
        person_role,
        keyword_count,
        ROW_NUMBER() OVER (PARTITION BY production_year ORDER BY keyword_count DESC) AS rank
    FROM MovieData
)
SELECT *
FROM RankedMovies
WHERE rank <= 5;
