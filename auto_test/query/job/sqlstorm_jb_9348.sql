
WITH movie_details AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        ct.kind AS cast_type,
        k.keyword AS movie_keyword,
        STRING_AGG(DISTINCT comp.name, ', ') AS companies
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        comp_cast_type ct ON c.person_role_id = ct.id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name comp ON mc.company_id = comp.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.title, t.production_year, a.name, ct.kind, k.keyword
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    cast_type,
    movie_keyword,
    companies
FROM 
    movie_details;
