WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        t.imdb_index, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorsInMovies AS (
    SELECT 
        c.movie_id, 
        ak.name AS actor_name, 
        COUNT(c.id) OVER (PARTITION BY c.movie_id) AS actor_count
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
),
MovieDetails AS (
    SELECT 
        rt.title_id, 
        rt.title, 
        rt.production_year, 
        a.actor_count
    FROM 
        RankedTitles rt
    LEFT JOIN 
        ActorsInMovies a ON rt.title_id = a.movie_id
    WHERE 
        rt.rank <= 5
)
SELECT 
    md.title, 
    md.production_year, 
    md.actor_count, 
    COUNT(DISTINCT mk.keyword_id) AS keyword_count
FROM 
    MovieDetails md
LEFT JOIN 
    movie_keyword mk ON md.title_id = mk.movie_id
GROUP BY 
    md.title, 
    md.production_year, 
    md.actor_count;
