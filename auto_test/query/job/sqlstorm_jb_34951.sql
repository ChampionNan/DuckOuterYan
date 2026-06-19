WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS depth
    FROM 
        aka_title mt
    WHERE 
        mt.production_year >= 2000
    UNION ALL
    SELECT 
        ml.linked_movie_id,
        m.title,
        m.production_year,
        depth + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title m ON ml.movie_id = m.id
    JOIN 
        movie_hierarchy mh ON mh.movie_id = ml.movie_id
    WHERE 
        mh.depth < 3
),
actor_role AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
),
movie_info_collection AS (
    SELECT 
        m.id AS movie_id,
        STRING_AGG(mi.info, ', ') AS movie_info
    FROM 
        aka_title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
    GROUP BY 
        m.id
)
SELECT 
    mh.movie_id,
    mh.title,
    mh.production_year,
    a.actor_name,
    a.role_name,
    COALESCE(mic.movie_info, 'No Info') AS movie_info_details
FROM 
    movie_hierarchy mh
LEFT JOIN 
    actor_role a ON mh.movie_id = a.movie_id AND a.actor_rank <= 3
LEFT JOIN 
    movie_info_collection mic ON mh.movie_id = mic.movie_id
WHERE 
    (mh.production_year BETWEEN 2000 AND 2023)
    AND (mic.movie_info IS NOT NULL OR mh.movie_id IN (SELECT movie_id FROM movie_info WHERE info_type_id = (SELECT id FROM info_type WHERE info = 'Box Office')));
