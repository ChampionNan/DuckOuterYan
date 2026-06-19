WITH RankedTitles AS (
    SELECT 
        at.movie_id,
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.title) as title_rank
    FROM 
        aka_title at
    WHERE 
        at.production_year IS NOT NULL
),
PersonRoles AS (
    SELECT 
        ci.movie_id,
        ci.role_id,
        COUNT(*) as role_count
    FROM 
        cast_info ci
    WHERE 
        ci.note IS NULL 
    GROUP BY 
        ci.movie_id, ci.role_id
),
CompanyInfo AS (
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
)
SELECT 
    rt.title,
    rt.production_year,
    pr.role_count,
    ci.company_name,
    ci.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    PersonRoles pr ON rt.movie_id = pr.movie_id
FULL OUTER JOIN 
    CompanyInfo ci ON rt.movie_id = ci.movie_id
WHERE 
    (pr.role_count > 1 OR pr.role_count IS NULL)
    AND rt.title_rank <= 10;
