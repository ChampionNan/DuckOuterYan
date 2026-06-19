
WITH RECURSIVE movie_hierarchy AS (
    
    SELECT 
        mt.id AS movie_id,
        mt.title,
        0 AS level,
        mt.production_year,
        NULL AS parent_movie_id
    FROM 
        aka_title mt 
    WHERE 
        mt.episode_of_id IS NULL

    UNION ALL

    
    SELECT 
        e.id AS movie_id,
        e.title,
        mh.level + 1 AS level,
        e.production_year,
        mh.movie_id AS parent_movie_id
    FROM 
        aka_title e
    JOIN movie_hierarchy mh ON e.episode_of_id = mh.movie_id
),


cast_details AS (
    SELECT 
        ci.movie_id,
        a.id AS actor_id,
        a.name AS actor_name,
        r.role AS actor_role,
        COALESCE(cct.kind, 'Unknown') AS cast_type
    FROM 
        cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    LEFT JOIN role_type r ON ci.role_id = r.id
    LEFT JOIN comp_cast_type cct ON ci.person_role_id = cct.id
),


keyword_details AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),


movie_cast_keywords AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        mh.parent_movie_id,
        cd.actor_id,
        cd.actor_name,
        cd.actor_role,
        cd.cast_type,
        COALESCE(kd.keywords, 'No keywords') AS keywords
    FROM 
        movie_hierarchy mh
    LEFT JOIN cast_details cd ON mh.movie_id = cd.movie_id
    LEFT JOIN keyword_details kd ON mh.movie_id = kd.movie_id
)


SELECT 
    mk.movie_id,
    mk.title,
    mk.production_year,
    mk.parent_movie_id,
    mk.actor_id,
    mk.actor_name,
    mk.actor_role,
    mk.cast_type,
    mk.keywords,
    COUNT(mk.actor_id) OVER (PARTITION BY mk.movie_id) AS actor_count,
    ROW_NUMBER() OVER (PARTITION BY mk.movie_id ORDER BY mk.actor_name) AS actor_rank
FROM 
    movie_cast_keywords mk
WHERE 
    mk.production_year BETWEEN 2000 AND 2020;
