WITH ranked_movies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM title t
    WHERE t.production_year IS NOT NULL
    AND t.title IS NOT NULL
),
actors_rank AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        RANK() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM cast_info c
    JOIN aka_name a ON c.person_id = a.person_id
    WHERE a.name IS NOT NULL
),
company_movies AS (
    SELECT 
        m.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM movie_companies m
    JOIN company_name c ON m.company_id = c.id
    JOIN company_type ct ON m.company_type_id = ct.id
    WHERE c.country_code IS NOT NULL
),
movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
),
final_output AS (
    SELECT 
        rm.title_id,
        rm.title,
        rm.production_year,
        ar.actor_name,
        ar.actor_rank,
        cm.company_name,
        cm.company_type,
        mk.keywords
    FROM ranked_movies rm
    LEFT JOIN actors_rank ar ON rm.title_id = ar.movie_id
    LEFT JOIN company_movies cm ON rm.title_id = cm.movie_id
    LEFT JOIN movie_keywords mk ON rm.title_id = mk.movie_id
    WHERE rm.year_rank <= 5
      AND (cm.company_type = 'Distributor' OR cm.company_type IS NULL)
)

SELECT 
    fo.title, 
    fo.production_year,
    fo.actor_name,
    COALESCE(fo.company_name, 'Unknown Company') AS company_name,
    COALESCE(fo.keywords, 'No Keywords') AS keywords
FROM final_output fo
WHERE (fo.actor_rank = 1 OR fo.actor_rank IS NULL);
