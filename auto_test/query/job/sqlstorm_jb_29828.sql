
WITH ActorMovies AS (
    SELECT 
        a.person_id,
        a.name AS actor_name,
        t.title AS movie_title,
        m.production_year,
        m.imdb_id,
        m.kind_id
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        aka_title t ON c.movie_id = t.movie_id
    JOIN 
        title m ON t.movie_id = m.id
    WHERE 
        m.production_year >= 2000
        AND m.production_year <= 2023
),
TopKeywords AS (
    SELECT 
        m.movie_id,
        k.keyword,
        COUNT(k.id) AS keyword_count
    FROM 
        movie_keyword m
    JOIN 
        keyword k ON m.keyword_id = k.id
    GROUP BY 
        m.movie_id, k.keyword
    ORDER BY 
        keyword_count DESC
    LIMIT 5
),
DirectorInfo AS (
    SELECT 
        d.name AS director_name,
        mc.movie_id
    FROM 
        company_name d
    JOIN 
        movie_companies mc ON d.id = mc.company_id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        ct.kind ILIKE '%director%'
)
SELECT 
    am.actor_name,
    am.movie_title,
    am.production_year,
    ti.info AS movie_info,
    tk.keyword,
    di.director_name
FROM 
    ActorMovies am
LEFT JOIN 
    movie_info ti ON am.imdb_id = ti.movie_id
LEFT JOIN 
    TopKeywords tk ON am.imdb_id = tk.movie_id
LEFT JOIN 
    DirectorInfo di ON am.imdb_id = di.movie_id
WHERE 
    ti.info_type_id = (SELECT id FROM info_type WHERE info ILIKE '%box office%');
