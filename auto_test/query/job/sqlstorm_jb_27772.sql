WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        ak.name AS actor_name,
        ak.id AS actor_id,
        c.role_id,
        rt.role AS actor_role,
        COUNT(DISTINCT mk.keyword_id) AS keyword_count
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.person_id 
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        role_type rt ON c.role_id = rt.id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.title, t.production_year, ak.name, ak.id, c.role_id, rt.role
),
TopMovies AS (
    SELECT 
        movie_title,
        production_year,
        actor_name,
        actor_id,
        actor_role,
        keyword_count,
        RANK() OVER (PARTITION BY production_year ORDER BY keyword_count DESC) AS rank
    FROM 
        MovieDetails
)
SELECT 
    production_year,
    movie_title,
    actor_name,
    actor_role,
    keyword_count
FROM 
    TopMovies
WHERE 
    rank <= 5;
