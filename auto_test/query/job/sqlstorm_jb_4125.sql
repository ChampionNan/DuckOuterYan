
WITH RankedMovies AS (
    SELECT 
        a.title, 
        a.production_year, 
        a.kind_id, 
        ROW_NUMBER() OVER (PARTITION BY a.kind_id ORDER BY a.production_year DESC) AS rn
    FROM 
        aka_title a
    WHERE 
        a.production_year IS NOT NULL
),
ActorsInfo AS (
    SELECT 
        ak.name AS actor_name, 
        c.movie_id, 
        COUNT(DISTINCT ak.person_id) AS actor_count
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    GROUP BY 
        ak.name, c.movie_id
),
MovieDetails AS (
    SELECT 
        t.title, 
        t.production_year, 
        COALESCE(ci.actor_count, 0) AS actor_count,
        t.id AS movie_id
    FROM 
        title t
    LEFT JOIN 
        ActorsInfo ci ON t.id = ci.movie_id
)
SELECT 
    md.title, 
    md.production_year, 
    md.actor_count, 
    CASE 
        WHEN md.actor_count > 5 THEN 'Ensemble Cast'
        WHEN md.actor_count > 0 AND md.actor_count <= 5 THEN 'Limited Cast'
        ELSE 'No Cast'
    END AS cast_size,
    COALESCE(k.keyword, 'No Keywords') AS keywords
FROM 
    MovieDetails md
LEFT JOIN 
    movie_keyword mk ON md.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    md.production_year >= 2000 
    AND md.production_year <= 2023
GROUP BY 
    md.title, 
    md.production_year, 
    md.actor_count, 
    k.keyword;
