WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
TopActors AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
),
MoviesWithActors AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        ta.actor_name
    FROM 
        RankedMovies rm
    LEFT JOIN 
        TopActors ta ON rm.movie_id = ta.movie_id
    WHERE 
        rm.title_rank <= 5
),
MoviesKeywords AS (
    SELECT 
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword m 
    JOIN 
        keyword k ON m.keyword_id = k.id
    GROUP BY 
        m.movie_id
)
SELECT 
    mwa.title,
    mwa.production_year,
    COALESCE(mwa.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(mk.keywords, 'No Keywords') AS keywords
FROM 
    MoviesWithActors mwa
LEFT JOIN 
    MoviesKeywords mk ON mwa.movie_id = mk.movie_id
WHERE 
    mwa.production_year >= 2000;
