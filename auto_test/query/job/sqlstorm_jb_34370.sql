WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        0 AS level
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
        movie_link ml
    JOIN 
        aka_title m ON ml.linked_movie_id = m.id
    JOIN 
        movie_hierarchy mh ON mh.movie_id = ml.movie_id
    WHERE 
        mh.level < 3  
)

SELECT 
    a.name AS actor_name,
    m.title AS movie_title,
    m.production_year,
    count(ci.id) OVER (PARTITION BY ci.movie_id) AS cast_count,
    CASE 
        WHEN m.production_year < 2010 THEN 'Classic'
        ELSE 'Modern'
    END AS movie_age_category,
    COALESCE(k.keyword, 'No Keyword') AS keyword_used,
    empty_comp.name AS empty_company_name
FROM 
    movie_hierarchy m
JOIN 
    cast_info ci ON m.movie_id = ci.movie_id
JOIN 
    aka_name a ON ci.person_id = a.person_id
LEFT JOIN 
    movie_keyword mk ON m.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_companies mc ON m.movie_id = mc.movie_id
LEFT JOIN 
    company_name empty_comp ON mc.company_id = empty_comp.id AND empty_comp.name IS NULL
WHERE 
    a.name IS NOT NULL
    AND m.title ILIKE '%adventure%';
