WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        COALESCE(e.title, 'Not an episode') AS episode_title,
        e.season_nr,
        e.episode_nr,
        0 AS depth
    FROM aka_title m
    LEFT JOIN aka_title e ON m.id = e.episode_of_id
    WHERE m.production_year IS NOT NULL
    
    UNION ALL
    
    SELECT 
        e.id,
        e.title,
        e.production_year,
        COALESCE(ee.title, 'Not an episode') AS episode_title,
        ee.season_nr,
        ee.episode_nr,
        mh.depth + 1
    FROM movie_hierarchy mh
    JOIN aka_title e ON mh.movie_id = e.episode_of_id
    LEFT JOIN aka_title ee ON e.id = ee.episode_of_id
    WHERE mh.depth < 5
),
distinct_cast AS (
    SELECT 
        DISTINCT c.person_id,
        c.movie_id,
        ka.name AS actor_name,
        r.role AS role
    FROM cast_info c
    JOIN aka_name ka ON c.person_id = ka.person_id
    JOIN role_type r ON c.role_id = r.id
),
movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
),
cast_with_ratings AS (
    SELECT 
        mo.movie_id,
        mo.title,
        d.actor_name,
        d.role,
        COALESCE(mk.keywords, 'No Keywords') AS keywords,
        ROW_NUMBER() OVER (PARTITION BY mo.movie_id ORDER BY d.actor_name) AS actor_order,
        RANK() OVER (PARTITION BY mo.movie_id ORDER BY d.role) AS role_rank
    FROM movie_hierarchy mo
    JOIN distinct_cast d ON mo.movie_id = d.movie_id
    LEFT JOIN movie_keywords mk ON mo.movie_id = mk.movie_id
)

SELECT 
    mh.title AS movie_title,
    mh.production_year,
    c.actor_name,
    c.role,
    c.keywords,
    c.actor_order,
    c.role_rank,
    CASE 
        WHEN c.actor_order IS NULL THEN 'Missing Actor Info'
        ELSE 'Actor Info Present'
    END AS actor_info_status,
    CASE 
        WHEN c.keywords IS NULL OR c.keywords = 'No Keywords' THEN 'No Keywords Available'
        ELSE 'Keywords Available'
    END AS keyword_status
FROM movie_hierarchy mh
LEFT JOIN cast_with_ratings c ON mh.movie_id = c.movie_id
WHERE mh.production_year BETWEEN 1990 AND 2023;
