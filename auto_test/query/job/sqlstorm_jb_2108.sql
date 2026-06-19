
WITH ranked_movies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.title) AS title_rank,
        COUNT(*) OVER (PARTITION BY m.production_year) AS total_movies
    FROM title m
    WHERE m.production_year IS NOT NULL
),
actor_counts AS (
    SELECT
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM cast_info c
    GROUP BY c.movie_id
),
detailed_movies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        ac.actor_count,
        CASE 
            WHEN ac.actor_count IS NULL THEN 'No Actors'
            WHEN ac.actor_count > 3 THEN 'Many Actors'
            ELSE 'Few Actors'
        END AS actor_category
    FROM ranked_movies rm
    LEFT JOIN actor_counts ac ON rm.movie_id = ac.movie_id
)
SELECT 
    dm.title,
    dm.production_year,
    dm.actor_count,
    dm.actor_category,
    k.keyword,
    COUNT(k.keyword) OVER (PARTITION BY dm.production_year) AS keyword_count,
    CASE 
        WHEN dm.actor_count IS NULL THEN 'Unknown'
        ELSE 'Known'
    END AS actor_status
FROM detailed_movies dm
LEFT JOIN movie_keyword mk ON dm.movie_id = mk.movie_id
LEFT JOIN keyword k ON mk.keyword_id = k.id
WHERE dm.production_year > 2000
GROUP BY 
    dm.title, 
    dm.production_year, 
    dm.actor_count, 
    dm.actor_category, 
    k.keyword;
