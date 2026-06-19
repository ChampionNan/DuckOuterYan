
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        1 AS level,
        NULL AS parent_id
    FROM 
        aka_title m
    WHERE 
        m.episode_of_id IS NULL
    
    UNION ALL

    SELECT 
        e.id AS movie_id,
        e.title,
        mh.level + 1,
        mh.movie_id AS parent_id
    FROM 
        aka_title e
    JOIN 
        movie_hierarchy mh ON e.episode_of_id = mh.movie_id
),

cast_details AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role,
        c.nr_order,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),

movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ',') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),

full_movie_details AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.level,
        COALESCE(cd.actor_name, 'No Cast') AS actor_name,
        COALESCE(cd.role, 'Unknown Role') AS role,
        COALESCE(mk.keywords, 'No Keywords') AS keywords,
        CASE 
            WHEN mh.level > 1 THEN 'Episode'
            ELSE 'Movie'
        END AS type_of_movie
    FROM 
        movie_hierarchy mh
    LEFT JOIN 
        cast_details cd ON mh.movie_id = cd.movie_id AND cd.actor_rank = 1
    LEFT JOIN 
        movie_keywords mk ON mh.movie_id = mk.movie_id
)

SELECT 
    fmd.movie_id,
    fmd.title,
    fmd.level,
    fmd.actor_name,
    fmd.role,
    fmd.keywords,
    fmd.type_of_movie
FROM 
    full_movie_details fmd
WHERE 
    fmd.keywords IS NOT NULL
    AND fmd.actor_name <> 'No Cast';
