WITH ranked_movies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
company_info AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        ct.kind IS NOT NULL
),
actor_movie_info AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.movie_id
),
final_output AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        cm.company_name,
        cm.company_type,
        ami.actor_count
    FROM 
        ranked_movies rm
    LEFT JOIN 
        company_info cm ON rm.movie_id = cm.movie_id
    LEFT JOIN 
        actor_movie_info ami ON rm.movie_id = ami.movie_id
)
SELECT 
    f.movie_id,
    f.title,
    f.production_year,
    COALESCE(f.company_name, 'No Company') AS company_name,
    COALESCE(f.company_type, 'Unknown') AS company_type,
    COALESCE(f.actor_count, 0) AS actor_count,
    CASE 
        WHEN f.production_year < 2000 THEN 'Classic'
        WHEN f.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS movie_era
FROM 
    final_output f
WHERE 
    f.actor_count > 0;
