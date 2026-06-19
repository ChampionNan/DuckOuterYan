WITH movie_actors AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        c.movie_id,
        t.title AS movie_title,
        t.production_year,
        t.kind_id
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        title t ON c.movie_id = t.id
    WHERE 
        a.name ILIKE '%Smith%' 
),

company_info AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),

keyword_info AS (
    SELECT 
        mk.movie_id,
        k.keyword AS movie_keyword
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),

movie_details AS (
    SELECT 
        ma.actor_id,
        ma.actor_name,
        ma.movie_id,
        ma.movie_title,
        ma.production_year,
        ci.company_name,
        ci.company_type,
        ki.movie_keyword
    FROM 
        movie_actors ma
    LEFT JOIN 
        company_info ci ON ma.movie_id = ci.movie_id
    LEFT JOIN 
        keyword_info ki ON ma.movie_id = ki.movie_id
)

SELECT 
    actor_name,
    movie_title,
    production_year,
    company_name,
    company_type,
    STRING_AGG(movie_keyword, ', ') AS keywords
FROM 
    movie_details
GROUP BY 
    actor_name, movie_title, production_year, company_name, company_type;
