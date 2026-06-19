WITH RankedTitles AS (
    SELECT 
        a.title,
        a.production_year,
        a.id AS title_id,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS title_rank,
        COUNT(*) OVER (PARTITION BY a.production_year) AS total_titles
    FROM 
        aka_title a
    WHERE 
        a.production_year IS NOT NULL
),
PersonRoles AS (
    SELECT 
        c.person_id,
        r.role AS role_name,
        COUNT(*) AS role_count
    FROM 
        cast_info c
    JOIN 
        role_type r ON c.role_id = r.id
    GROUP BY 
        c.person_id, r.role
),
CompanyDetails AS (
    SELECT 
        m.movie_id,
        comp.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY m.movie_id ORDER BY comp.name) AS company_rank
    FROM 
        movie_companies m
    JOIN 
        company_name comp ON m.company_id = comp.id
    JOIN 
        company_type ct ON m.company_type_id = ct.id
)
SELECT 
    rt.title,
    rt.production_year,
    COALESCE(pr.role_name, 'Unknown Role') AS role_name,
    COALESCE(pr.role_count, 0) AS role_count,
    c.company_name,
    c.company_type,
    rt.title_rank,
    rt.total_titles,
    (CASE 
         WHEN rt.total_titles = 0 THEN NULL 
         ELSE (rt.title_rank * 1.0 / rt.total_titles) 
     END) AS title_rank_ratio
FROM 
    RankedTitles rt
LEFT JOIN 
    PersonRoles pr ON pr.person_id = rt.title_id
LEFT JOIN 
    CompanyDetails c ON c.movie_id = rt.title_id
WHERE 
    rt.production_year >= 2000;
