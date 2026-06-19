
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        1 AS level,
        NULL AS parent_movie_id
    FROM 
        aka_title AS t
    WHERE 
        t.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT 
        et.id AS movie_id,
        et.title,
        et.production_year,
        mh.level + 1 AS level,
        mh.movie_id AS parent_movie_id
    FROM 
        aka_title AS et
    JOIN 
        MovieHierarchy AS mh ON et.episode_of_id = mh.movie_id
)

SELECT
    m.title AS movie_title,
    m.production_year,
    COALESCE(p.name, 'Unknown') AS person_name,
    r.role AS role_type,
    COUNT(*) OVER (PARTITION BY m.movie_id) AS total_cast,
    (SELECT COUNT(DISTINCT kc.keyword) 
     FROM movie_keyword AS mk
     JOIN keyword AS kc ON mk.keyword_id = kc.id
     WHERE mk.movie_id = m.movie_id) AS total_keywords,
    CASE
        WHEN m.production_year < 2000 THEN 'Classic'
        WHEN m.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS movie_categorization
FROM 
    MovieHierarchy AS m
LEFT JOIN 
    complete_cast AS cc ON m.movie_id = cc.movie_id
LEFT JOIN 
    cast_info AS ci ON cc.subject_id = ci.person_id
LEFT JOIN 
    aka_name AS p ON ci.person_id = p.person_id
LEFT JOIN 
    role_type AS r ON ci.role_id = r.id
WHERE 
    m.level <= 3
    AND p.name IS NOT NULL
    AND m.title IS NOT NULL
GROUP BY 
    m.movie_id,
    m.title,
    m.production_year,
    p.name,
    r.role,
    m.level;
