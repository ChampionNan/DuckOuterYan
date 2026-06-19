WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
    UNION ALL
    SELECT 
        m.id,
        m.title,
        m.production_year,
        mh.title_rank
    FROM 
        MovieHierarchy mh
    JOIN 
        aka_title m ON mh.movie_id = m.episode_of_id
)
, CastRoles AS (
    SELECT 
        ci.movie_id,
        r.role,
        COUNT(*) AS role_count
    FROM 
        cast_info ci
    JOIN 
        role_type r ON ci.role_id = r.id
    GROUP BY 
        ci.movie_id, r.role
)
, CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    mh.title, 
    mh.production_year,
    COALESCE(cr.role, 'No Role Assigned') AS actor_role,
    cr.role_count,
    cd.company_name,
    cd.company_type
FROM 
    MovieHierarchy mh
LEFT JOIN 
    CastRoles cr ON mh.movie_id = cr.movie_id
LEFT JOIN 
    CompanyDetails cd ON mh.movie_id = cd.movie_id
WHERE 
    mh.production_year >= 2000 
    AND (cr.role IS NOT NULL OR cd.company_name IS NOT NULL);
