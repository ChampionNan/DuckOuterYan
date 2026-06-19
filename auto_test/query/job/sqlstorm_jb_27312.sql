WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS rank
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year IS NOT NULL
),
TopRankedTitles AS (
    SELECT 
        title_id, 
        title, 
        production_year, 
        keyword 
    FROM 
        RankedTitles
    WHERE 
        rank <= 5
),
CastDetails AS (
    SELECT 
        c.movie_id,
        c.person_id,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type,
        COUNT(mc.company_id) AS total_companies
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        mc.movie_id, cn.name, ct.kind
)
SELECT 
    tt.title,
    tt.production_year,
    tt.keyword,
    cd.actor_name,
    cd.role_name,
    comp.company_name,
    comp.company_type,
    comp.total_companies
FROM 
    TopRankedTitles tt
LEFT JOIN 
    CastDetails cd ON tt.title_id = cd.movie_id
LEFT JOIN 
    CompanyDetails comp ON tt.title_id = comp.movie_id;
