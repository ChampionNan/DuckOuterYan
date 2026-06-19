
WITH MovieDetails AS (
    SELECT 
        mt.title AS movie_title,
        mt.production_year,
        ak.name AS actor_name,
        ac.nr_order AS role_order,
        rt.role AS role_name,
        STRING_AGG(DISTINCT kw.keyword, ', ') AS keywords
    FROM 
        aka_title mt
    JOIN 
        complete_cast cc ON mt.id = cc.movie_id
    JOIN 
        cast_info ac ON cc.subject_id = ac.id
    JOIN 
        aka_name ak ON ac.person_id = ak.person_id
    JOIN 
        role_type rt ON ac.role_id = rt.id
    LEFT JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    LEFT JOIN 
        keyword kw ON mk.keyword_id = kw.id
    WHERE 
        mt.production_year >= 2000
    GROUP BY 
        mt.title, mt.production_year, ak.name, ac.nr_order, rt.role
),
Ranking AS (
    SELECT 
        md.movie_title,
        md.production_year,
        md.actor_name,
        md.role_order,
        md.role_name,
        md.keywords,
        ROW_NUMBER() OVER (PARTITION BY md.movie_title ORDER BY md.role_order) AS actor_rank
    FROM 
        MovieDetails md
)
SELECT 
    r.movie_title,
    r.production_year,
    r.actor_name,
    r.role_name,
    r.actor_rank,
    r.keywords
FROM 
    Ranking r
WHERE 
    r.actor_rank <= 5;
