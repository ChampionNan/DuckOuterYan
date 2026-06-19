WITH RankedMovies AS (
    SELECT 
        t.title, 
        t.production_year, 
        c.kind AS movie_kind, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS movie_rank
    FROM 
        aka_title t
    JOIN 
        kind_type c ON t.kind_id = c.id
    WHERE 
        t.production_year IS NOT NULL
),
TopMovies AS (
    SELECT 
        title, 
        production_year, 
        movie_kind
    FROM 
        RankedMovies
    WHERE 
        movie_rank <= 5
),
MovieCast AS (
    SELECT 
        m.title,
        m.production_year,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        TopMovies m
    LEFT JOIN 
        complete_cast cc ON m.production_year = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.movie_id = ci.movie_id
    LEFT JOIN 
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN 
        role_type r ON ci.role_id = r.id
)
SELECT 
    mc.title,
    mc.production_year,
    mc.actor_name,
    COALESCE(mc.role_name, 'Unspecified') AS role_name,
    CASE 
        WHEN mc.production_year < 2000 THEN 'Classic'
        WHEN mc.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS era_label
FROM 
    MovieCast mc;
