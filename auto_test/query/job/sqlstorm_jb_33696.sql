WITH RECURSIVE movie_hierarchy AS (
    
    SELECT
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        m.episode_of_id,
        1 AS level
    FROM title m
    WHERE m.episode_of_id IS NULL

    UNION ALL

    SELECT
        e.id AS movie_id,
        e.title AS movie_title,
        e.production_year,
        e.episode_of_id,
        h.level + 1
    FROM title e
    JOIN movie_hierarchy h ON e.episode_of_id = h.movie_id
),

movie_cast_info AS (
    
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        a.name AS actor_name,
        c.role_id,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY c.nr_order) AS actor_rank
    FROM title t
    JOIN cast_info c ON t.id = c.movie_id
    JOIN aka_name a ON c.person_id = a.person_id
    JOIN role_type r ON c.role_id = r.id
),

movie_keywords AS (
    
    SELECT
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword m
    JOIN keyword k ON m.keyword_id = k.id
    GROUP BY m.movie_id
),

final_summary AS (
    
    SELECT
        mh.movie_id,
        mh.movie_title,
        mh.production_year,
        COALESCE(mc.actor_name, 'Unknown Actor') AS actor_name,
        COALESCE(mk.keywords, 'No Keywords') AS keywords,
        mh.level
    FROM movie_hierarchy mh
    LEFT JOIN movie_cast_info mc ON mh.movie_id = mc.movie_id AND mc.actor_rank <= 3 
    LEFT JOIN movie_keywords mk ON mh.movie_id = mk.movie_id
)

SELECT 
    f.movie_title,
    f.production_year,
    f.actor_name,
    f.keywords,
    f.level
FROM final_summary f
WHERE f.level = 1;
