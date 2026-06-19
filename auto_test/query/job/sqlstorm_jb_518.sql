
WITH RankedMovies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.production_year DESC, mt.title ASC) AS rank
    FROM 
        aka_title mt
    WHERE 
        mt.production_year IS NOT NULL
), 
CastInfoWithRoles AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        rt.role,
        COUNT(ci.id) OVER (PARTITION BY ci.movie_id) AS total_casts
    FROM 
        cast_info ci
    JOIN 
        role_type rt ON ci.role_id = rt.id
), 
ActorNames AS (
    SELECT 
        an.person_id,
        STRING_AGG(an.name, ', ') AS actor_names
    FROM 
        aka_name an
    GROUP BY 
        an.person_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    COALESCE(an.actor_names, 'No Cast') AS actors,
    cwr.total_casts,
    CASE 
        WHEN cwr.total_casts > 5 THEN 'Large Cast'
        WHEN cwr.total_casts BETWEEN 3 AND 5 THEN 'Medium Cast'
        ELSE 'Small Cast'
    END AS cast_size
FROM 
    RankedMovies rm
LEFT JOIN 
    CastInfoWithRoles cwr ON rm.movie_id = cwr.movie_id
LEFT JOIN 
    ActorNames an ON cwr.person_id = an.person_id
WHERE 
    rm.rank <= 3
GROUP BY 
    rm.movie_id, 
    rm.title, 
    rm.production_year, 
    an.actor_names, 
    cwr.total_casts;
