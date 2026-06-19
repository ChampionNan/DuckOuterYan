WITH MovieDetails AS (
    SELECT 
        t.id AS movie_id,
        t.title AS movie_title,
        t.production_year,
        rt.role AS role_type,
        a.name AS actor_name,
        c.name AS company_name,
        m.info AS movie_description,
        COUNT(k.id) AS keyword_count
    FROM 
        aka_title t
    JOIN 
        cast_info ci ON t.id = ci.movie_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        movie_info m ON t.id = m.movie_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
        AND c.country_code = 'USA'
        AND m.info_type_id IN (SELECT id FROM info_type WHERE info = 'Overview')
    GROUP BY 
        t.id, t.title, t.production_year, rt.role, a.name, c.name, m.info
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    role_type,
    company_name,
    movie_description,
    keyword_count
FROM 
    MovieDetails;
