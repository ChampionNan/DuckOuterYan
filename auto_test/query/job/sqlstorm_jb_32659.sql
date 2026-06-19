
WITH RECURSIVE MovieCTE AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        1 AS level
    FROM 
        aka_title t
    WHERE
        t.production_year >= 2000

    UNION ALL

    SELECT 
        m.movie_id,
        m.title,
        m.production_year,
        cte.level + 1
    FROM 
        movie_link ml
    INNER JOIN 
        MovieCTE cte ON ml.movie_id = cte.movie_id
    INNER JOIN 
        aka_title m ON ml.linked_movie_id = m.id
    WHERE 
        cte.level < 3  
),

CastWithRoles AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_rank
    FROM 
        cast_info ci
    LEFT JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN 
        role_type rt ON ci.role_id = rt.id
),

MovieCompanies AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(DISTINCT cn.name, ', ') AS companies
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    GROUP BY 
        mc.movie_id
)

SELECT 
    m.title,
    m.production_year,
    COALESCE(cwr.actor_name, 'Unknown Actor') AS lead_actor,
    COALESCE(cwr.role_name, 'No Role Specified') AS role,
    COALESCE(mc.companies, 'No Companies') AS production_companies
FROM 
    MovieCTE m
LEFT JOIN 
    CastWithRoles cwr ON m.movie_id = cwr.movie_id AND cwr.role_rank = 1
LEFT JOIN 
    MovieCompanies mc ON m.movie_id = mc.movie_id
LEFT JOIN 
    movie_info mi ON m.movie_id = mi.movie_id AND mi.info_type_id = (
        SELECT id 
        FROM info_type 
        WHERE info = 'tagline'
    )
LEFT JOIN 
    aka_title at ON m.movie_id = at.id
WHERE 
    at.title IS NOT NULL
    AND (m.production_year BETWEEN 2000 AND 2023 OR m.production_year IS NULL) 
GROUP BY 
    m.title, 
    m.production_year, 
    cwr.actor_name, 
    cwr.role_name, 
    mc.companies;
