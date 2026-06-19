WITH RankedMovies AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY t.production_year DESC) AS rn
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.movie_id
    WHERE 
        t.production_year IS NOT NULL
),
TopMovies AS (
    SELECT 
        actor_id,
        actor_name,
        movie_title,
        production_year
    FROM 
        RankedMovies
    WHERE 
        rn <= 3
),
MovieKeywords AS (
    SELECT 
        mt.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        aka_title mt ON mk.movie_id = mt.movie_id
    GROUP BY 
        mt.movie_id
),
MovieDetails AS (
    SELECT 
        tm.actor_id,
        tm.actor_name,
        tm.movie_title,
        tm.production_year,
        COALESCE(mk.keywords, 'No Keywords') AS keywords
    FROM 
        TopMovies tm
    LEFT JOIN 
        MovieKeywords mk ON mk.movie_id = (SELECT id FROM aka_title WHERE title = tm.movie_title LIMIT 1)
)
SELECT 
    md.actor_name,
    md.movie_title,
    md.production_year,
    md.keywords,
    COALESCE(mp.info, 'No Additional Info') AS extra_info
FROM 
    MovieDetails md
LEFT JOIN 
    movie_info mp ON md.movie_title = (SELECT title FROM aka_title WHERE id = mp.movie_id LIMIT 1)
WHERE 
    md.production_year >= 2000;
