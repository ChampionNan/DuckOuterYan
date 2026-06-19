WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.id DESC) AS rn
    FROM 
        aka_title m
    WHERE 
        m.production_year >= 2000
),
ActorRoles AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        COUNT(c.id) AS role_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
    GROUP BY 
        c.movie_id, a.name, r.role
),
CompanyInformation AS (
    SELECT 
        m.movie_id,
        co.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies m
    JOIN 
        company_name co ON m.company_id = co.id
    JOIN 
        company_type ct ON m.company_type_id = ct.id
)
SELECT 
    rm.title,
    rm.production_year,
    ar.actor_name,
    ar.role_name,
    ci.company_name,
    ci.company_type,
    CASE 
        WHEN ar.role_count IS NULL THEN 'No Roles Listed'
        ELSE ar.role_count::TEXT
    END AS role_count
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorRoles ar ON rm.movie_id = ar.movie_id
LEFT JOIN 
    CompanyInformation ci ON rm.movie_id = ci.movie_id
WHERE 
    (rm.production_year IS NOT NULL OR rm.production_year IS NULL) 
    AND (ar.role_name LIKE '%Lead%' OR ar.role_name IS NULL);
