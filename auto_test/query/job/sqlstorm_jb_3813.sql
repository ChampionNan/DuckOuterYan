WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
), 
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    INNER JOIN 
        company_name c ON mc.company_id = c.id
    INNER JOIN 
        company_type ct ON mc.company_type_id = ct.id
), 
CastRoles AS (
    SELECT 
        ci.movie_id, 
        r.role, 
        COUNT(*) AS role_count
    FROM 
        cast_info ci
    INNER JOIN 
        role_type r ON ci.person_role_id = r.id
    GROUP BY 
        ci.movie_id, r.role
), 
KeywordMovies AS (
    SELECT 
        mk.movie_id, 
        k.keyword
    FROM 
        movie_keyword mk
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword IS NOT NULL
)
SELECT 
    rt.title AS Movie_Title,
    rt.production_year AS Year,
    cm.company_name AS Production_Company,
    cr.role AS Role,
    cr.role_count AS Number_of_Roles,
    km.keyword AS Keywords
FROM 
    RankedTitles rt
LEFT JOIN 
    CompanyMovies cm ON cm.movie_id = rt.title_id
LEFT JOIN 
    CastRoles cr ON cr.movie_id = rt.title_id
LEFT JOIN 
    KeywordMovies km ON km.movie_id = rt.title_id
WHERE 
    rt.year_rank <= 5;
