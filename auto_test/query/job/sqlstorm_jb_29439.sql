WITH RankedMovies AS (
    SELECT 
        at.title AS movie_title,
        at.production_year,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY at.id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        aka_title at
    JOIN 
        cast_info ci ON at.id = ci.movie_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    WHERE 
        at.production_year BETWEEN 2000 AND 2023
),
FilteredMovies AS (
    SELECT 
        movie_title,
        production_year,
        STRING_AGG(actor_name, ', ') AS actors_list
    FROM 
        RankedMovies
    WHERE 
        actor_rank <= 3
    GROUP BY 
        movie_title, production_year
)
SELECT 
    fm.movie_title,
    fm.production_year,
    fm.actors_list,
    ct.kind AS company_type,
    km.keyword AS movie_keyword
FROM 
    FilteredMovies fm
LEFT JOIN 
    movie_companies mc ON mc.movie_id = (SELECT id FROM aka_title WHERE title = fm.movie_title AND production_year = fm.production_year LIMIT 1)
LEFT JOIN 
    company_type ct ON mc.company_type_id = ct.id 
LEFT JOIN 
    movie_keyword mk ON mk.movie_id = (SELECT id FROM aka_title WHERE title = fm.movie_title AND production_year = fm.production_year LIMIT 1)
LEFT JOIN 
    keyword km ON mk.keyword_id = km.id
WHERE 
    fm.production_year IS NOT NULL;
