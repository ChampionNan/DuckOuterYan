
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        1 AS level
    FROM 
        aka_title m
    WHERE 
        m.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')

    UNION ALL

    SELECT 
        m.id AS movie_id,
        CONCAT(m.title, ' (Linked)') AS title,
        m.production_year,
        mh.level + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title m ON ml.linked_movie_id = m.id
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 3  
),
ranked_movies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        RANK() OVER (PARTITION BY mh.production_year ORDER BY mh.level DESC) AS movie_rank
    FROM 
        movie_hierarchy mh
),
movie_counts AS (
    SELECT 
        m.title,
        COUNT(*) AS total_links
    FROM 
        movie_link ml
    JOIN 
        aka_title m ON ml.movie_id = m.id
    GROUP BY 
        m.title
),
actor_movie AS (
    SELECT 
        a.name AS actor_name,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY t.production_year DESC) AS appearance_order
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.id
    WHERE 
        a.name IS NOT NULL
)
SELECT 
    am.actor_name,
    am.title,
    am.production_year,
    COALESCE(mb.total_links, 0) AS total_links,
    CASE 
        WHEN r.movie_rank IS NULL THEN 'Not Ranked'
        ELSE CONCAT('Ranked ', CAST(r.movie_rank AS TEXT))
    END AS ranking_info
FROM 
    actor_movie am
LEFT JOIN 
    ranked_movies r ON am.title = r.title AND am.production_year = r.production_year
LEFT JOIN 
    movie_counts mb ON am.title = mb.title
WHERE 
    am.appearance_order <= 5;
