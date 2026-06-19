
WITH ranked_titles AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        k.keyword AS genre,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        t.id AS movie_id
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
),
actor_casting AS (
    SELECT 
        a.name AS actor_name,
        c.movie_id,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    WHERE 
        c.nr_order IS NOT NULL
),
company_info AS (
    SELECT 
        c.name AS company_name,
        mc.movie_id,
        STRING_AGG(DISTINCT ct.kind, ', ') AS company_types
    FROM 
        company_name c
    JOIN 
        movie_companies mc ON c.id = mc.company_id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        c.name, mc.movie_id
),
final_output AS (
    SELECT 
        rt.movie_title,
        rt.production_year,
        rt.genre,
        ac.actor_name,
        ci.company_name,
        ci.company_types,
        rt.title_rank,
        ac.actor_rank
    FROM 
        ranked_titles rt
    LEFT JOIN 
        actor_casting ac ON rt.movie_id = ac.movie_id
    LEFT JOIN 
        company_info ci ON rt.movie_id = ci.movie_id
)
SELECT 
    movie_title,
    production_year,
    genre,
    actor_name,
    company_name,
    company_types
FROM 
    final_output
WHERE 
    title_rank <= 5 AND actor_rank <= 3;
