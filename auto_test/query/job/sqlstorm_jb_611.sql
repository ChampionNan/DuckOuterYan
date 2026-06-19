WITH ranked_movies AS (
    SELECT 
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC, at.title) AS rank_by_year
    FROM 
        aka_title at
    WHERE 
        at.production_year > 2000
),
actors_in_movies AS (
    SELECT 
        ak.name AS actor_name,
        am.title AS movie_title,
        am.production_year,
        COUNT(ci.person_id) AS actor_count
    FROM 
        cast_info ci
    INNER JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    INNER JOIN 
        aka_title am ON ci.movie_id = am.movie_id
    GROUP BY 
        ak.name, am.title, am.production_year
),
company_info AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
final_results AS (
    SELECT 
        rm.title,
        rm.production_year,
        a.actor_name,
        a.actor_count,
        c.company_name,
        RANK() OVER (PARTITION BY rm.production_year ORDER BY a.actor_count DESC) AS rank_by_actor_count,
        COALESCE(c.company_type, 'Independent') AS company_type
    FROM 
        ranked_movies rm
    LEFT JOIN 
        actors_in_movies a ON rm.title = a.movie_title AND rm.production_year = a.production_year
    LEFT JOIN 
        company_info c ON rm.title = (SELECT title FROM aka_title WHERE movie_id = c.movie_id LIMIT 1)
    WHERE 
        rm.rank_by_year <= 5
)
SELECT 
    title,
    production_year,
    actor_name,
    actor_count,
    company_name,
    company_type,
    rank_by_actor_count
FROM 
    final_results
WHERE 
    actor_count IS NOT NULL AND
    (company_name IS NOT NULL OR company_type = 'Independent');
