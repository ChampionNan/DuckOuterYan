
WITH RECURSIVE movie_hierarchy AS (
    
    SELECT 
        m.id AS movie_id,
        m.title,
        1 AS level,
        NULL AS parent_movie_id
    FROM 
        aka_title m 
    WHERE 
        m.episode_of_id IS NULL  

    UNION ALL

    
    SELECT 
        m.id,
        m.title,
        mh.level + 1,
        mh.movie_id AS parent_movie_id 
    FROM 
        aka_title m 
    JOIN 
        movie_hierarchy mh ON m.episode_of_id = mh.movie_id
),

ranked_cast AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
),

movies_with_keywords AS (
    SELECT 
        m.id AS movie_id,
        ARRAY_AGG(k.keyword) AS keywords
    FROM 
        aka_title m 
    JOIN 
        movie_keyword mk ON m.id = mk.movie_id 
    JOIN 
        keyword k ON mk.keyword_id = k.id 
    GROUP BY 
        m.id
)

SELECT 
    mh.movie_id,
    mh.title AS movie_title,
    mh.level AS hierarchy_level,
    COALESCE(rk.actor_name, 'No Actor') AS main_actor,
    COALESCE(mk.keywords, '{}') AS associated_keywords
FROM 
    movie_hierarchy mh
LEFT JOIN 
    ranked_cast rk ON mh.movie_id = rk.movie_id AND rk.actor_rank = 1
LEFT JOIN 
    movies_with_keywords mk ON mh.movie_id = mk.movie_id
GROUP BY 
    mh.movie_id, mh.title, mh.level, rk.actor_name, mk.keywords;
