WITH MovieCast AS (
    SELECT 
        t.title AS movie_title,
        c.nr_order,
        a.name AS actor_name,
        r.role AS role_title,
        t.production_year
    FROM 
        title t
    INNER JOIN 
        cast_info c ON t.id = c.movie_id
    INNER JOIN 
        aka_name a ON c.person_id = a.person_id
    INNER JOIN 
        role_type r ON c.role_id = r.id
    WHERE 
        t.production_year >= 2000
), CompanyInfo AS (
    SELECT 
        t.title AS movie_title,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        title t
    INNER JOIN 
        movie_companies mc ON t.id = mc.movie_id
    INNER JOIN 
        company_name cn ON mc.company_id = cn.id
    INNER JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        cn.country_code = 'USA'
), MovieKeywords AS (
    SELECT 
        t.title AS movie_title,
        k.keyword 
    FROM 
        title t
    INNER JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword LIKE '%action%'
)
SELECT 
    mc.movie_title,
    mc.actor_name,
    mc.role_title,
    mc.production_year,
    ci.company_name,
    ci.company_type,
    mk.keyword
FROM 
    MovieCast mc
LEFT JOIN 
    CompanyInfo ci ON mc.movie_title = ci.movie_title
LEFT JOIN 
    MovieKeywords mk ON mc.movie_title = mk.movie_title;
