WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000  
),

PersonRoles AS (
    SELECT 
        ci.person_id,
        ci.movie_id,
        r.role,
        COUNT(*) AS role_count
    FROM 
        cast_info ci
    JOIN 
        role_type r ON ci.role_id = r.id
    GROUP BY 
        ci.person_id, ci.movie_id, r.role
),

CompanyDetails AS (
    SELECT 
        mc.movie_id,
        cmp.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cmp ON mc.company_id = cmp.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)

SELECT 
    rt.title_id,
    rt.title,
    rt.production_year,
    rt.keyword,
    pr.role,
    pr.role_count,
    cd.company_name,
    cd.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    PersonRoles pr ON rt.title_id = pr.movie_id
LEFT JOIN 
    CompanyDetails cd ON rt.title_id = cd.movie_id
WHERE 
    rt.year_rank <= 5;
