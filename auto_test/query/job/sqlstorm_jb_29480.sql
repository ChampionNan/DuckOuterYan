WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        c.name AS company_name,
        r.role AS cast_role,
        ak.name AS actor_name,
        t.production_year,
        k.keyword AS movie_keyword,
        p.info AS person_info
    FROM 
        title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        person_info p ON ci.person_id = p.person_id
    WHERE 
        t.production_year BETWEEN 2000 AND 2023
        AND (p.info_type_id IN (SELECT id FROM info_type WHERE info IN ('Biography', 'Awards')))
),
Ranking AS (
    SELECT 
        movie_title,
        company_name,
        actor_name,
        cast_role,
        production_year,
        movie_keyword,
        ROW_NUMBER() OVER (PARTITION BY movie_title ORDER BY actor_name) AS actor_rank
    FROM 
        MovieDetails
)
SELECT 
    movie_title,
    company_name,
    actor_name,
    cast_role,
    production_year,
    movie_keyword,
    actor_rank
FROM 
    Ranking
WHERE 
    actor_rank <= 3;
