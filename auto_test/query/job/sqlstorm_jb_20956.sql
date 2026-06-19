WITH ranked_movies AS (
    SELECT 
        title.id AS movie_id,
        title.title AS movie_title,
        title.production_year,
        ROW_NUMBER() OVER (PARTITION BY title.production_year ORDER BY title.id) AS rank_within_year
    FROM title
    WHERE title.production_year IS NOT NULL
),
cast_with_roles AS (
    SELECT 
        cast_info.movie_id,
        aka_name.name AS actor_name,
        role_type.role AS actor_role,
        CASE 
            WHEN cast_info.note IS NOT NULL THEN 'Note: ' || cast_info.note 
            ELSE 'No notes available' 
        END AS notes
    FROM cast_info
    JOIN aka_name ON cast_info.person_id = aka_name.person_id
    JOIN role_type ON cast_info.role_id = role_type.id
),
movies_with_keyword AS (
    SELECT 
        movie_id,
        STRING_AGG(keyword.keyword, ', ') AS keywords
    FROM movie_keyword
    JOIN keyword ON movie_keyword.keyword_id = keyword.id
    GROUP BY movie_id
),
final_output AS (
    SELECT 
        rm.movie_title,
        rm.production_year,
        cwr.actor_name,
        cwr.actor_role,
        mwk.keywords,
        CASE 
            WHEN rm.rank_within_year BETWEEN 1 AND 5 THEN 'Top 5 in Year'
            WHEN rm.rank_within_year IS NULL THEN 'Not Ranked'
            ELSE 'Lower Ranked'
        END AS ranking_description
    FROM ranked_movies rm
    LEFT JOIN cast_with_roles cwr ON rm.movie_id = cwr.movie_id
    LEFT JOIN movies_with_keyword mwk ON rm.movie_id = mwk.movie_id
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    actor_role,
    keywords,
    ranking_description
FROM final_output
WHERE 
    (ranking_description = 'Top 5 in Year' AND actor_role IS NOT NULL)
    OR (keywords IS NOT NULL AND keywords LIKE '%Action%');
