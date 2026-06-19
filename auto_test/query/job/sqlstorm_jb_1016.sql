WITH MovieRoles AS (
    SELECT 
        ct.role AS role_name,
        ca.movie_id,
        COUNT(DISTINCT ca.person_id) AS total_actors
    FROM 
        cast_info ca
    JOIN 
        role_type ct ON ca.role_id = ct.id
    GROUP BY 
        ct.role, ca.movie_id
),
MovieDetails AS (
    SELECT 
        mt.title,
        mt.production_year,
        mct.kind AS company_type,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY mt.id ORDER BY mt.production_year DESC) AS rn
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_companies mc ON mt.id = mc.movie_id
    LEFT JOIN 
        company_type mct ON mc.company_type_id = mct.id
    LEFT JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
)
SELECT 
    md.title,
    md.production_year,
    COALESCE(mr.role_name, 'Unknown') AS role_name,
    md.company_type,
    md.keyword,
    md.rn AS rank_position,
    NULLIF(mr.total_actors, 0) AS actors_count
FROM 
    MovieDetails md
LEFT JOIN 
    MovieRoles mr ON md.production_year = mr.movie_id
WHERE 
    (md.production_year >= 2000 AND md.production_year <= 2023) 
    AND (md.keyword IS NOT NULL OR md.company_type IS NOT NULL);
