WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        0 AS level
    FROM 
        aka_title m
    WHERE 
        m.production_year >= 2000
    UNION ALL
    SELECT 
        m.id,
        m.title,
        m.production_year,
        mh.level + 1
    FROM 
        aka_title m
    INNER JOIN 
        MovieHierarchy mh ON m.episode_of_id = mh.movie_id
),
RankedMovies AS (
    SELECT 
        m.movie_id,
        m.movie_title,
        m.production_year,
        RANK() OVER (PARTITION BY m.production_year ORDER BY m.movie_title) AS title_rank,
        COUNT(DISTINCT c.person_id) AS total_cast
    FROM 
        MovieHierarchy m
    LEFT JOIN 
        cast_info c ON m.movie_id = c.movie_id
    GROUP BY 
        m.movie_id, m.movie_title, m.production_year
)
SELECT 
    rm.production_year,
    rm.movie_title,
    rm.title_rank,
    rm.total_cast,
    CASE 
        WHEN rm.total_cast > 10 THEN 'Large Cast'
        WHEN rm.total_cast IS NULL THEN 'No Cast Data'
        ELSE 'Small Cast'
    END AS cast_size,
    COALESCE(k.keyword, 'No Keyword') AS movie_keyword
FROM 
    RankedMovies rm
LEFT JOIN 
    movie_keyword mk ON rm.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    rm.production_year IS NOT NULL
    AND (rm.movie_title ILIKE '%adventure%' OR rm.movie_title ILIKE '%fantasy%');
