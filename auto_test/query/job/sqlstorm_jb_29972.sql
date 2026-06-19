
WITH MovieDetails AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        p.id AS person_id,
        p.name AS person_name,
        ra.role AS role_name,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM 
        aka_title m
    JOIN 
        complete_cast cc ON m.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.id = ci.movie_id
    JOIN 
        role_type ra ON ci.role_id = ra.id
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        m.id, m.title, m.production_year, p.id, p.name, ra.role
),
TopMovies AS (
    SELECT 
        movie_id,
        movie_title,
        production_year,
        person_id,
        person_name,
        role_name,
        keywords,
        ROW_NUMBER() OVER (PARTITION BY production_year ORDER BY production_year DESC) AS rn
    FROM 
        MovieDetails
)
SELECT 
    tm.movie_title,
    tm.production_year,
    tm.person_name,
    tm.role_name,
    tm.keywords AS all_keywords
FROM 
    TopMovies tm
WHERE 
    tm.rn <= 5;
