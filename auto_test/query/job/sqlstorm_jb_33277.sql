
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        CAST(NULL AS VARCHAR) AS parent_title,
        0 AS level
    FROM 
        aka_title t
    WHERE 
        t.episode_of_id IS NULL

    UNION ALL

    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        mh.title AS parent_title,
        mh.level + 1
    FROM 
        aka_title t
    JOIN 
        MovieHierarchy mh ON t.episode_of_id = mh.movie_id
),
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        mh.parent_title,
        mh.level,
        ROW_NUMBER() OVER (PARTITION BY mh.production_year ORDER BY mh.level DESC) AS rn
    FROM 
        MovieHierarchy mh
)
SELECT 
    m.movie_id,
    m.title,
    m.production_year,
    m.parent_title,
    COALESCE(cast_info.role_id, -1) AS role_id,
    COUNT(*) OVER (PARTITION BY m.movie_id) AS cast_count,
    STRING_AGG(DISTINCT cn.name, ', ') AS company_names
FROM 
    RankedMovies m
LEFT JOIN 
    cast_info ON m.movie_id = cast_info.movie_id
LEFT JOIN 
    movie_companies mc ON m.movie_id = mc.movie_id
LEFT JOIN 
    company_name cn ON mc.company_id = cn.imdb_id
WHERE 
    m.level <= 1
    AND (m.production_year IS NOT NULL AND m.production_year > 2000)
GROUP BY 
    m.movie_id, m.title, m.production_year, m.parent_title, cast_info.role_id;
