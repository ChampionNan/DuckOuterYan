WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rn,
        COUNT(CASE WHEN k.keyword IS NOT NULL THEN 1 END) OVER (PARTITION BY t.id) AS keyword_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE 'movie%')
), 
CoActors AS (
    SELECT 
        ci.movie_id, 
        string_agg(a.name, ', ') AS coactors
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    GROUP BY 
        ci.movie_id
) 
SELECT 
    rm.title, 
    rm.production_year, 
    COALESCE(ca.coactors, 'No co-actors') AS coactors, 
    rm.keyword_count
FROM 
    RankedMovies rm
LEFT JOIN 
    CoActors ca ON rm.movie_id = ca.movie_id
WHERE 
    rm.rn <= 5;
