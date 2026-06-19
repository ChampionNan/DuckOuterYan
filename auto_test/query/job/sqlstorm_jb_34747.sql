WITH RECURSIVE movie_series AS (
    
    SELECT
        mt.id AS movie_id,
        mt.title,
        1 AS series_depth
    FROM
        aka_title mt
    WHERE
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT
        e.id AS movie_id,
        e.title,
        ms.series_depth + 1
    FROM
        aka_title e
    JOIN
        movie_series ms ON e.episode_of_id = ms.movie_id
),
top_movies AS (
    
    SELECT
        mt.id,
        mt.title,
        mt.production_year,
        RANK() OVER (PARTITION BY mt.production_year ORDER BY mt.production_year DESC) AS year_rank
    FROM
        aka_title mt
    WHERE
        mt.production_year IS NOT NULL
),
movie_details AS (
    
    SELECT
        mt.title AS movie_title,
        mt.production_year,
        ak.name AS actor_name,
        STRING_AGG(kw.keyword, ', ') AS keywords
    FROM
        aka_title mt
    LEFT JOIN
        cast_info ci ON ci.movie_id = mt.id
    LEFT JOIN
        aka_name ak ON ak.person_id = ci.person_id
    LEFT JOIN
        movie_keyword mk ON mk.movie_id = mt.id
    LEFT JOIN
        keyword kw ON kw.id = mk.keyword_id
    WHERE
        ci.nr_order IS NOT NULL
    GROUP BY
        mt.id, ak.name, mt.title, mt.production_year
)

SELECT 
    md.movie_title,
    md.production_year,
    md.actor_name,
    CASE
        WHEN ms.series_depth IS NOT NULL THEN 'Part of a Series'
        ELSE 'Standalone Movie'
    END AS movie_type,
    COALESCE(md.keywords, 'No keywords') AS keywords
FROM 
    movie_details md
LEFT JOIN 
    movie_series ms ON md.movie_title = ms.title
WHERE 
    md.production_year IN (SELECT production_year FROM top_movies WHERE year_rank <= 10);
