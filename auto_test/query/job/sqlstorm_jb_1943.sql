
WITH MovieDetails AS (
    SELECT 
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY a.name) AS actor_rank
    FROM 
        aka_name a
        JOIN cast_info c ON a.person_id = c.person_id
        JOIN title t ON c.movie_id = t.id
        JOIN role_type r ON c.role_id = r.id
),
HighRankedMovies AS (
    SELECT 
        md.movie_title,
        md.production_year,
        md.actor_name,
        md.role_name,
        COUNT(*) OVER (PARTITION BY md.movie_title) AS actor_count
    FROM 
        MovieDetails md
    WHERE 
        md.actor_rank <= 3
),
NullRoleMovies AS (
    SELECT 
        t.title AS movie_title,
        COUNT(DISTINCT c.person_id) AS cast_count
    FROM 
        title t
        LEFT JOIN cast_info c ON t.id = c.movie_id
    WHERE 
        c.role_id IS NULL
    GROUP BY 
        t.title
),
AllMovies AS (
    SELECT 
        h.movie_title,
        h.production_year,
        h.actor_name,
        h.role_name,
        h.actor_count,
        n.cast_count
    FROM 
        HighRankedMovies h
    FULL OUTER JOIN NullRoleMovies n ON h.movie_title = n.movie_title
)
SELECT 
    am.movie_title,
    am.production_year,
    CAST(am.production_year AS VARCHAR) AS year_str,
    COALESCE(am.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(am.role_name, 'Unknown Role') AS role_name,
    NULLIF(am.actor_count, 0) AS total_actors,
    COALESCE(am.cast_count, 0) AS null_role_count
FROM 
    AllMovies am
WHERE 
    (am.actor_count > 5 OR (am.cast_count IS NOT NULL AND am.cast_count > 0));
