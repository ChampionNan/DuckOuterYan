WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.title IS NOT NULL
),
filtered_cast AS (
    SELECT 
        c.person_id,
        c.movie_id,
        COALESCE(rc.role, 'Unknown') AS role,
        COUNT(*) OVER (PARTITION BY c.person_id) AS movies_count
    FROM 
        cast_info c
    LEFT JOIN 
        role_type rc ON c.role_id = rc.id
    WHERE 
        rc.role IS NOT NULL OR c.role_id IS NULL
),
movie_info_count AS (
    SELECT 
        mi.movie_id,
        COUNT(mi.id) AS info_count
    FROM 
        movie_info mi
    WHERE 
        mi.info IS NOT NULL
    GROUP BY 
        mi.movie_id
)
SELECT 
    a.name AS actor_name,
    rt.title AS movie_title,
    rt.production_year,
    fcast.role,
    fcast.movies_count,
    COALESCE(mic.info_count, 0) AS additional_info_count
FROM 
    aka_name a
JOIN 
    filtered_cast fcast ON a.person_id = fcast.person_id
JOIN 
    ranked_titles rt ON fcast.movie_id = rt.title_id
LEFT JOIN 
    movie_info_count mic ON mic.movie_id = fcast.movie_id
WHERE 
    rt.title_rank <= 5 
    AND (fcast.movies_count BETWEEN 2 AND 10 OR fcast.role IS NULL);
