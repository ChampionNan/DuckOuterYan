
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        1 AS depth
    FROM 
        aka_title mt
    WHERE 
        mt.production_year > 2000  
    UNION ALL
    SELECT 
        ml.linked_movie_id AS movie_id,
        at.title AS movie_title,
        mh.depth + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title at ON ml.linked_movie_id = at.id
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.depth < 5  
),
ranked_movies AS (
    SELECT 
        mh.movie_id,
        mh.movie_title,
        RANK() OVER (PARTITION BY mh.depth ORDER BY mh.movie_title) AS rank,
        mh.depth
    FROM 
        movie_hierarchy mh
),
cast_details AS (
    SELECT 
        c.movie_id, 
        a.name AS actor_name,
        COALESCE(r.role, 'Unknown') AS role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    LEFT JOIN 
        role_type r ON c.role_id = r.id
),
keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keyword_list
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.movie_title,
    rm.rank,
    cd.actor_name,
    cd.role,
    cd.actor_rank,
    k.keyword_list
FROM 
    ranked_movies rm
LEFT JOIN 
    cast_details cd ON rm.movie_id = cd.movie_id AND cd.actor_rank <= 5  
LEFT JOIN 
    keywords k ON rm.movie_id = k.movie_id
WHERE 
    (cd.actor_name IS NOT NULL OR k.keyword_list IS NULL);
