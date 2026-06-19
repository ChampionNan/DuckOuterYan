WITH RecursiveActorRoles AS (
    SELECT c.person_id, c.movie_id, c.role_id, r.role, 
           ROW_NUMBER() OVER(PARTITION BY c.person_id ORDER BY c.nr_order) AS role_ranking
    FROM cast_info c
    JOIN role_type r ON c.role_id = r.id
),

MovieKeywordMapping AS (
    SELECT mk.movie_id, ARRAY_AGG(k.keyword) AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
),

DetailedMovieInfo AS (
    SELECT m.id AS movie_id, m.title, 
           COALESCE(a.name, 'Unknown') AS actor_name,
           COALESCE(k.keywords, '{}') AS keywords,
           EXTRACT(YEAR FROM cast('2024-10-01' as date)) - m.production_year AS movie_age,
           DENSE_RANK() OVER (PARTITION BY m.kind_id ORDER BY m.production_year DESC) AS recent_rank
    FROM aka_title m
    LEFT JOIN aka_name a ON a.id = (
        SELECT ci.person_id FROM cast_info ci 
        WHERE ci.movie_id = m.movie_id 
        ORDER BY ci.nr_order LIMIT 1
    )
    LEFT JOIN MovieKeywordMapping k ON m.id = k.movie_id
    WHERE m.production_year IS NOT NULL 
    AND m.title NOT LIKE '%untitled%'
),

FilteredMovies AS (
    SELECT d.*, 
           CASE 
               WHEN d.movie_age < 5 THEN 'Recent'
               WHEN d.movie_age < 10 THEN 'Moderate'
               ELSE 'Old'
           END AS age_category
    FROM DetailedMovieInfo d
    WHERE d.recent_rank <= 5
)

SELECT f.movie_id, f.title, f.actor_name, f.keywords, f.age_category,
       CASE WHEN f.keywords = '{}' THEN 'No Keywords' ELSE 'Has Keywords' END AS keyword_status
FROM FilteredMovies f
LEFT JOIN movie_info mi ON f.movie_id = mi.movie_id 
AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Rating')
WHERE mi.info IS NOT NULL;
