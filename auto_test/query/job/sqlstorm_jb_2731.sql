WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
CastDetails AS (
    SELECT 
        ca.movie_id,
        a.name AS actor_name,
        COALESCE(r.role, 'Unknown') AS role
    FROM 
        cast_info ca
    LEFT JOIN 
        aka_name a ON ca.person_id = a.person_id
    LEFT JOIN 
        role_type r ON ca.role_id = r.id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
MovieInfo AS (
    SELECT 
        mi.movie_id,
        STRING_AGG(DISTINCT mi.info, ', ') AS info_list
    FROM 
        movie_info mi
    WHERE 
        mi.note IS NOT NULL
    GROUP BY 
        mi.movie_id
)
SELECT 
    rt.title,
    rt.production_year,
    cd.actor_name,
    cd.role,
    COALESCE(ci.company_name, 'Independent') AS company_name,
    COALESCE(ci.company_type, 'N/A') AS company_type,
    mi.info_list
FROM 
    RankedTitles rt
LEFT JOIN 
    CastDetails cd ON rt.title_id = cd.movie_id
LEFT JOIN 
    CompanyDetails ci ON rt.title_id = ci.movie_id
LEFT JOIN 
    MovieInfo mi ON rt.title_id = mi.movie_id
WHERE 
    rt.title_rank <= 5;
