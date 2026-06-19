WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        kc.kind AS kind,
        count(mk.keyword_id) AS keyword_count
    FROM 
        title m
    JOIN 
        kind_type kc ON m.kind_id = kc.id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    GROUP BY 
        m.id, m.title, m.production_year, kc.kind
),
TopMovies AS (
    SELECT 
        * 
    FROM 
        RankedMovies
    WHERE 
        keyword_count > 5
    ORDER BY 
        production_year DESC
    LIMIT 10
),
MovieDetails AS (
    SELECT 
        tm.movie_id,
        tm.movie_title,
        tm.production_year,
        c.name AS company_name,
        a.name AS actor_name,
        r.role AS role_title
    FROM 
        TopMovies tm
    LEFT JOIN 
        movie_companies mc ON tm.movie_id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    LEFT JOIN 
        cast_info ci ON tm.movie_id = ci.movie_id
    LEFT JOIN 
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN 
        role_type r ON ci.role_id = r.id
)

SELECT 
    md.movie_title,
    md.production_year,
    md.company_name,
    md.actor_name,
    md.role_title
FROM 
    MovieDetails md;
