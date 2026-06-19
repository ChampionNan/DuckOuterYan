
WITH ranked_titles AS (
    SELECT 
        t.title, 
        t.production_year, 
        k.keyword, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank,
        t.id
    FROM 
        title t
    INNER JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
), 
cast_details AS (
    SELECT 
        c.movie_id, 
        a.name AS actor_name, 
        r.role
    FROM 
        cast_info c
    INNER JOIN 
        aka_name a ON c.person_id = a.person_id
    INNER JOIN 
        role_type r ON c.role_id = r.id
),
company_info AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    INNER JOIN 
        company_name cn ON mc.company_id = cn.id
    INNER JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    rt.title,
    rt.production_year,
    rt.keyword,
    cd.actor_name,
    cd.role,
    ci.company_name,
    ci.company_type
FROM 
    ranked_titles rt
LEFT JOIN 
    cast_details cd ON rt.id = cd.movie_id
LEFT JOIN 
    company_info ci ON rt.id = ci.movie_id
WHERE 
    rt.rank <= 5;
