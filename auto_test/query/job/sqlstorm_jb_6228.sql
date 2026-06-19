WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        c.kind AS company_type,
        k.keyword AS movie_keyword,
        i.info AS movie_info
    FROM title t
    JOIN cast_info ci ON t.id = ci.movie_id
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN movie_companies mc ON t.id = mc.movie_id
    JOIN company_type c ON mc.company_type_id = c.id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    LEFT JOIN movie_info mi ON t.id = mi.movie_id
    LEFT JOIN info_type i ON mi.info_type_id = i.id
    WHERE t.production_year BETWEEN 2000 AND 2020
      AND c.kind IN ('Production', 'Distribution')
),
RankedMovies AS (
    SELECT 
        movie_title,
        production_year,
        actor_name,
        company_type,
        movie_keyword,
        movie_info,
        ROW_NUMBER() OVER (PARTITION BY movie_title ORDER BY production_year DESC) AS rank
    FROM MovieDetails
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    company_type,
    movie_keyword,
    movie_info
FROM RankedMovies
WHERE rank = 1;
