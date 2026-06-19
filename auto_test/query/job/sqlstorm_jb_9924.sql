
WITH movie_data AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.name AS company_name,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords,
        a.name AS actor_name,
        p.info AS actor_info
    FROM 
        aka_title AS t
    JOIN 
        movie_companies AS mc ON t.id = mc.movie_id
    JOIN 
        company_name AS c ON mc.company_id = c.id
    JOIN 
        complete_cast AS cc ON t.id = cc.movie_id
    JOIN 
        cast_info AS ci ON cc.subject_id = ci.id
    JOIN 
        aka_name AS a ON ci.person_id = a.person_id
    LEFT JOIN 
        movie_keyword AS mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword AS k ON mk.keyword_id = k.id
    LEFT JOIN 
        person_info AS p ON a.person_id = p.person_id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.title, t.production_year, c.name, a.name, p.info
)
SELECT 
    movie_title,
    production_year,
    company_name,
    keywords,
    actor_name,
    actor_info
FROM 
    movie_data;
