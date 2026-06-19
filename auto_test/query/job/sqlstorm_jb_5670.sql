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
FilteredCompanies AS (
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
    WHERE 
        ct.kind = 'Distributor'
),
CastRoles AS (
    SELECT 
        ci.movie_id,
        r.role,
        COUNT(ci.person_id) AS role_count
    FROM 
        cast_info ci
    JOIN 
        role_type r ON ci.role_id = r.id
    GROUP BY 
        ci.movie_id, r.role
),
FinalResults AS (
    SELECT 
        rt.title,
        rt.production_year,
        fc.company_name,
        fc.company_type,
        cr.role,
        cr.role_count
    FROM 
        RankedTitles rt
    LEFT JOIN 
        FilteredCompanies fc ON rt.title_id = fc.movie_id
    LEFT JOIN 
        CastRoles cr ON rt.title_id = cr.movie_id
    WHERE 
        rt.title_rank <= 5
)
SELECT 
    title,
    production_year,
    company_name,
    company_type,
    role,
    role_count
FROM 
    FinalResults;
