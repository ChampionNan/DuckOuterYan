WITH movie_actors AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS actor_role
    FROM
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
movie_facts AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        COUNT(k.id) AS keyword_count
    FROM 
        aka_title m
    JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        m.id, m.title, m.production_year
),
company_details AS (
    SELECT 
        mc.movie_id,
        com.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name com ON mc.company_id = com.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
final_report AS (
    SELECT 
        mf.title AS movie_title,
        mf.production_year,
        ma.actor_name,
        ma.actor_role,
        cd.company_name,
        cd.company_type,
        mf.keyword_count
    FROM 
        movie_facts mf
    LEFT JOIN 
        movie_actors ma ON mf.movie_id = ma.movie_id
    LEFT JOIN 
        company_details cd ON mf.movie_id = cd.movie_id
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    actor_role,
    company_name,
    company_type,
    keyword_count
FROM 
    final_report
WHERE 
    production_year >= 2000;
