
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        mt.production_year,
        mt.kind_id,
        0 AS level
    FROM 
        aka_title mt
    WHERE 
        mt.production_year BETWEEN 2000 AND 2020
    UNION ALL
    SELECT 
        ml.linked_movie_id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        m.kind_id,
        mh.level + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title m ON ml.linked_movie_id = m.id
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 2
), 
cast_roles AS (
    SELECT 
        c.movie_id, 
        a.name AS actor_name, 
        r.role AS role_type, 
        COUNT(*) OVER (PARTITION BY c.movie_id) AS actor_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
), 
info_with_keywords AS (
    SELECT 
        mi.movie_id,
        mi.info AS movie_info,
        ARRAY_AGG(DISTINCT k.keyword) AS keywords
    FROM 
        movie_info mi
    JOIN 
        movie_keyword mk ON mi.movie_id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mi.movie_id, mi.info
)

SELECT 
    mh.movie_id,
    mh.movie_title,
    mh.production_year,
    cr.actor_name,
    cr.role_type,
    cr.actor_count,
    iw.movie_info,
    iw.keywords,
    CASE 
        WHEN cr.actor_count > 5 THEN 'Large Ensemble'
        WHEN cr.actor_count BETWEEN 3 AND 5 THEN 'Medium Ensemble'
        ELSE 'Small Ensemble' 
    END AS ensemble_size
FROM 
    movie_hierarchy mh
LEFT JOIN 
    cast_roles cr ON mh.movie_id = cr.movie_id
LEFT JOIN 
    info_with_keywords iw ON mh.movie_id = iw.movie_id
WHERE 
    mh.kind_id IN (SELECT id FROM kind_type WHERE kind IN ('movie', 'tv series'))
    AND (iw.keywords IS NOT NULL OR iw.movie_info IS NOT NULL);
