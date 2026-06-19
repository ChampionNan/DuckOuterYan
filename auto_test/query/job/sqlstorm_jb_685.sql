WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY COUNT(DISTINCT c.person_id) DESC) AS cast_rank
    FROM 
        aka_title t
    LEFT JOIN 
        cast_info c ON t.id = c.movie_id
    GROUP BY 
        t.id, t.title, t.production_year
), ActorRoles AS (
    SELECT 
        a.name AS actor_name,
        c.movie_id,
        r.role AS role_name,
        COUNT(*) OVER (PARTITION BY a.id, c.movie_id) AS role_count
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    LEFT JOIN 
        role_type r ON c.role_id = r.id
), FilteredActors AS (
    SELECT 
        actor_name,
        movie_id,
        role_name,
        role_count
    FROM 
        ActorRoles
    WHERE 
        role_count > 1
)

SELECT 
    rm.title,
    rm.production_year,
    fa.actor_name,
    fa.role_name,
    fa.role_count
FROM 
    RankedMovies rm
JOIN 
    FilteredActors fa ON rm.title_id = fa.movie_id
WHERE 
    rm.cast_rank <= 5;
