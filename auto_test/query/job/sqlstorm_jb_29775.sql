WITH RankedTitles AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        k.keyword AS movie_keyword,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
),
CastDetails AS (
    SELECT 
        t.title AS movie_title,
        a.name AS actor_name,
        cr.role AS role_name,
        c.nr_order
    FROM 
        cast_info c
    JOIN 
        title t ON c.movie_id = t.id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type cr ON c.role_id = cr.id
    WHERE 
        cr.role LIKE 'Actor%'
),
CompanyDetails AS (
    SELECT 
        t.title AS movie_title,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        title t ON mc.movie_id = t.id
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        cn.country_code = 'USA'
)
SELECT 
    rt.movie_title,
    rt.production_year,
    rt.movie_keyword,
    cd.actor_name,
    cd.role_name,
    cd.nr_order,
    co.company_name,
    co.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    CastDetails cd ON rt.movie_title = cd.movie_title AND rt.keyword_rank = 1
LEFT JOIN 
    CompanyDetails co ON rt.movie_title = co.movie_title
WHERE 
    rt.keyword_rank = 1;
