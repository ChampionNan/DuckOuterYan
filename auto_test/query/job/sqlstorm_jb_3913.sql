WITH ranked_movies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
actors_movies AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        c.movie_id,
        COUNT(c.movie_id) OVER (PARTITION BY a.id) AS movie_count
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
),
movie_keyword_counts AS (
    SELECT 
        mk.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM 
        movie_keyword mk
    GROUP BY 
        mk.movie_id
)
SELECT 
    r.title_id,
    r.title,
    r.production_year,
    am.actor_name,
    COALESCE(mkc.keyword_count, 0) AS keyword_count,
    am.movie_count,
    CASE 
        WHEN am.movie_count > 5 THEN 'Prolific Actor'
        ELSE 'Occasional Actor'
    END AS actor_type
FROM 
    ranked_movies r
LEFT JOIN 
    actors_movies am ON r.title_id = am.movie_id
LEFT JOIN 
    movie_keyword_counts mkc ON r.title_id = mkc.movie_id
WHERE 
    r.year_rank <= 10;
