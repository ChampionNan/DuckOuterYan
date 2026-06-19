
WITH RECURSIVE movie_actors AS (
    SELECT 
        c.movie_id, 
        a.person_id, 
        a.name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    WHERE 
        a.name IS NOT NULL
),
filtered_movies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        COUNT(DISTINCT ma.person_id) AS actor_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_actors ma ON t.id = ma.movie_id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.id, t.title, t.production_year, t.kind_id
)
SELECT 
    f.movie_id,
    f.title,
    f.production_year,
    f.actor_count,
    COALESCE(c.name, 'Unknown Company') AS company_name,
    k.keyword AS movie_keyword
FROM 
    filtered_movies f
LEFT JOIN 
    movie_companies mc ON f.movie_id = mc.movie_id
LEFT JOIN 
    company_name c ON mc.company_id = c.id
LEFT JOIN 
    movie_keyword mk ON f.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    f.actor_count > 10;
