WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_by_year
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
MovieRoles AS (
    SELECT 
        c.movie_id,
        r.role,
        COUNT(c.person_id) AS role_count
    FROM 
        cast_info c
    INNER JOIN 
        role_type r ON c.role_id = r.id
    GROUP BY 
        c.movie_id, r.role
),
FilteredMovies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(mr.role_count, 0) AS total_roles
    FROM 
        RankedMovies rm
    LEFT JOIN 
        MovieRoles mr ON rm.movie_id = mr.movie_id
    WHERE 
        rm.rank_by_year <= 5
)
SELECT 
    DISTINCT fn.name AS actor_name,
    fm.title AS movie_title,
    fm.production_year,
    fm.total_roles,
    CASE 
        WHEN fm.total_roles = 0 THEN 'No roles assigned'
        ELSE 'Roles assigned'
    END AS role_status
FROM 
    FilteredMovies fm
LEFT JOIN 
    cast_info ci ON fm.movie_id = ci.movie_id
LEFT JOIN 
    aka_name fn ON ci.person_id = fn.person_id
WHERE 
    fn.person_id IS NOT NULL;
