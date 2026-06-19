WITH movie_data AS (
    SELECT 
        t.id AS title_id, 
        t.title AS movie_title, 
        t.production_year, 
        ak.name AS actor_name, 
        ak.person_id,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY ak.name) AS actor_rank,
        COUNT(*) OVER (PARTITION BY t.id) AS total_actors
    FROM 
        aka_title AS t
    LEFT JOIN 
        cast_info AS ci ON t.id = ci.movie_id
    LEFT JOIN 
        aka_name AS ak ON ci.person_id = ak.person_id
    WHERE 
        t.production_year IS NOT NULL
),
company_data AS (
    SELECT 
        mc.movie_id, 
        c.name AS company_name, 
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS company_rank
    FROM 
        movie_companies AS mc
    JOIN 
        company_name AS c ON mc.company_id = c.id
    JOIN 
        company_type AS ct ON mc.company_type_id = ct.id
),
keyword_data AS (
    SELECT 
        mk.movie_id, 
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword AS mk
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
final_data AS (
    SELECT 
        md.title_id,
        md.movie_title,
        md.production_year,
        md.actor_name,
        md.actor_rank,
        md.total_actors,
        cd.company_name,
        cd.company_type,
        kd.keywords
    FROM 
        movie_data AS md
    LEFT JOIN 
        company_data AS cd ON md.title_id = cd.movie_id AND cd.company_rank = 1
    LEFT JOIN 
        keyword_data AS kd ON md.title_id = kd.movie_id
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    actor_rank,
    total_actors,
    COALESCE(company_name, 'N/A') AS company_name,
    COALESCE(company_type, 'Unknown') AS company_type,
    COALESCE(keywords, 'No keywords') AS keywords
FROM 
    final_data
WHERE 
    total_actors > 1 
    AND (production_year BETWEEN 1980 AND 2020)
    AND (company_type IS NOT NULL OR keywords IS NOT NULL);
