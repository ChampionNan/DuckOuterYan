WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        1 AS level
    FROM 
        aka_title m
    WHERE 
        m.production_year >= 2000  
    UNION ALL
    SELECT 
        m.id AS movie_id,
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
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.title) AS title_rank,
        COUNT(CASE WHEN c.role_id IS NOT NULL THEN 1 END) OVER (PARTITION BY m.id) AS cast_count
    FROM 
        aka_title m
    LEFT JOIN 
        cast_info c ON m.id = c.movie_id
),
KeywordCounts AS (
    SELECT 
        mk.movie_id,
        COUNT(k.id) AS keyword_count
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    mh.movie_id,
    mh.title,
    mh.production_year,
    COALESCE(kc.keyword_count, 0) AS keyword_count,
    rm.cast_count,
    CASE 
        WHEN rm.cast_count > 10 THEN 'Large Cast'
        ELSE 'Small Cast'
    END AS cast_size,
    CASE 
        WHEN mh.level IS NULL THEN 'No Episodes'
        ELSE CONCAT('Level ', mh.level)
    END AS hierarchy_level
FROM 
    MovieHierarchy mh
LEFT JOIN 
    RankedMovies rm ON mh.movie_id = rm.movie_id
LEFT JOIN 
    KeywordCounts kc ON mh.movie_id = kc.movie_id;
