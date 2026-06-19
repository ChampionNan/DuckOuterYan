WITH movie_info_cte AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        mi.info,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY mi.note DESC) AS rn
    FROM 
        title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
    WHERE 
        mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'Synopsis')
),
actor_counts AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.movie_id
),
joined_data AS (
    SELECT 
        m.movie_id,
        m.title,
        m.info,
        COALESCE(ac.actor_count, 0) AS actor_count,
        ROW_NUMBER() OVER (ORDER BY m.title) AS movie_rank
    FROM 
        movie_info_cte m
    LEFT JOIN 
        actor_counts ac ON m.movie_id = ac.movie_id
)
SELECT 
    jd.title,
    jd.info,
    jd.actor_count,
    'Rank: ' || jd.movie_rank AS movie_rank_string,
    CASE 
        WHEN jd.actor_count > 0 THEN 'Popular Movie'
        ELSE 'Less Popular Movie' 
    END AS popularity_label
FROM 
    joined_data jd
WHERE 
    jd.info IS NOT NULL;
