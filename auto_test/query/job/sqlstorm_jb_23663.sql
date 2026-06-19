WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(c.id) OVER (PARTITION BY t.id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        cast_info c ON t.id = c.movie_id
    WHERE 
        t.production_year IS NOT NULL
),
DirectorInfo AS (
    SELECT 
        ci.movie_id,
        a.name AS director_name
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    WHERE 
        ci.role_id = (SELECT id FROM role_type WHERE role = 'Director')
),
KeywordStats AS (
    SELECT 
        mk.movie_id,
        COUNT(DISTINCT k.id) AS unique_keywords_count
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.title_rank,
    di.director_name,
    COALESCE(ks.unique_keywords_count, 0) AS unique_keywords_count,
    rm.cast_count,
    CASE WHEN rm.cast_count > 10 THEN 'Large Cast'
         WHEN rm.cast_count BETWEEN 5 AND 10 THEN 'Medium Cast'
         ELSE 'Small Cast' END AS cast_size_category
FROM 
    RankedMovies rm
LEFT JOIN 
    DirectorInfo di ON rm.movie_id = di.movie_id
LEFT JOIN 
    KeywordStats ks ON rm.movie_id = ks.movie_id
WHERE 
    (rm.title_rank = 1 OR rm.production_year >= 2000)
    AND di.director_name IS NOT NULL;
