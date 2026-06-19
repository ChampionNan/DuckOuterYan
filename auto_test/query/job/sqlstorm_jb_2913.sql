
WITH RankedMovies AS (
    SELECT 
        m.title, 
        m.production_year, 
        m.kind_id, 
        ROW_NUMBER() OVER (PARTITION BY m.kind_id ORDER BY m.production_year DESC) AS rn,
        m.id AS movie_id
    FROM 
        aka_title m
),
ActorsWithRoles AS (
    SELECT 
        a.name AS actor_name, 
        c.movie_id, 
        r.role AS role_name, 
        COUNT(*) OVER (PARTITION BY a.id) AS total_roles
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MoviesWithInfo AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        COALESCE(mi.info, 'No info') AS info
    FROM 
        aka_title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
)
SELECT 
    rm.title,
    rm.production_year,
    COALESCE(aw.actor_name, 'Unknown Actor') AS actor_name,
    aw.role_name,
    aw.total_roles,
    CASE 
        WHEN rm.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE '%Drama%') THEN 'Drama'
        WHEN rm.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE '%Comedy%') THEN 'Comedy'
        ELSE 'Other'
    END AS genre,
    COALESCE(mwi.info, 'No additional information') AS additional_info
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorsWithRoles aw ON rm.movie_id = aw.movie_id
LEFT JOIN 
    MoviesWithInfo mwi ON rm.movie_id = mwi.movie_id
WHERE 
    rm.rn <= 10;
