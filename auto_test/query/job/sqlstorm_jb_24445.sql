WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank,
        COUNT(*) OVER (PARTITION BY t.production_year) AS year_movie_count
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
        AND t.production_year BETWEEN 1990 AND 2020
),
ActorRoles AS (
    SELECT 
        ci.movie_id, 
        ak.name AS actor_name,
        rt.role AS role_name,
        COUNT(*) AS role_count
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ak.person_id = ci.person_id
    LEFT JOIN 
        role_type rt ON rt.id = ci.role_id
    GROUP BY 
        ci.movie_id, ak.name, rt.role
),
CoStars AS (
    SELECT 
        a1.movie_id,
        a2.actor_name AS co_star_name
    FROM 
        ActorRoles a1
    JOIN 
        ActorRoles a2 ON a1.movie_id = a2.movie_id AND a1.actor_name <> a2.actor_name
)
SELECT 
    rm.title,
    rm.production_year,
    ar.actor_name,
    COALESCE(cr.co_star_name, 'No co-stars') AS co_star_name,
    ar.role_name,
    CASE 
        WHEN ar.role_count > 1 THEN 'Multiple roles'
        ELSE 'Single role'
    END AS role_summary,
    CASE 
        WHEN rm.year_movie_count > 10 THEN 'Highly prolific year'
        ELSE 'Moderate year'
    END AS year_prolificacy
FROM 
    RankedMovies rm
JOIN 
    ActorRoles ar ON rm.movie_id = ar.movie_id
LEFT JOIN 
    CoStars cr ON ar.movie_id = cr.movie_id AND ar.actor_name = cr.co_star_name
WHERE 
    rm.rank <= 5;
