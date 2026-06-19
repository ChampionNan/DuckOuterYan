WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year, 
        CAST(m.title AS TEXT) AS path
    FROM 
        aka_title m
    WHERE 
        m.production_year IS NOT NULL
    
    UNION ALL
    
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year, 
        CAST(CONCAT(h.path, ' -> ', m.title) AS TEXT)
    FROM 
        aka_title m
    JOIN 
        movie_hierarchy h ON h.movie_id = m.episode_of_id
),
ranked_movies AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.title) AS title_rank,
        COUNT(c.person_id) OVER (PARTITION BY m.id) AS num_cast
    FROM 
        aka_title m
    LEFT JOIN 
        cast_info c ON m.id = c.movie_id
    WHERE 
        m.production_year IS NOT NULL
),
movie_keywords AS (
    SELECT 
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        ranked_movies m ON mk.movie_id = m.movie_id
    GROUP BY 
        m.movie_id
),
selected_movies AS (
    SELECT 
        mh.movie_id, 
        mh.title, 
        mh.production_year, 
        mh.path, 
        rm.title_rank, 
        rm.num_cast,
        mk.keywords
    FROM 
        movie_hierarchy mh
    JOIN 
        ranked_movies rm ON mh.movie_id = rm.movie_id
    LEFT JOIN 
        movie_keywords mk ON mh.movie_id = mk.movie_id
    WHERE 
        (mh.production_year >= 2000 AND mh.production_year < 2020)
        OR 
        (mh.title ILIKE '%A%')
        AND 
        mk.keywords IS NOT NULL
)
SELECT 
    sm.title,
    sm.production_year,
    sm.num_cast,
    sm.keywords,
    CASE 
        WHEN sm.num_cast IS NULL THEN 'No Cast Info'
        WHEN sm.num_cast > 10 THEN 'Large Cast'
        ELSE 'Small Cast'
    END AS cast_size,
    COALESCE(NULLIF(sm.keywords, ''), 'No Keywords') AS final_keywords
FROM 
    selected_movies sm
WHERE 
    sm.title_rank BETWEEN 1 AND 5;
