WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        COALESCE(t.production_year, 0) AS production_year,
        ROW_NUMBER() OVER (PARTITION BY COALESCE(t.production_year, 0) ORDER BY t.production_year DESC) AS rank,
        COUNT(*) OVER (PARTITION BY COALESCE(t.production_year, 0)) AS movie_count
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NULL OR t.production_year BETWEEN 1980 AND 2023
),
ActorRoles AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name, 
        r.role AS role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS role_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS all_keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.movie_count,
    ar.actor_name,
    ar.role,
    ar.role_rank,
    mk.all_keywords
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorRoles ar ON rm.movie_id = ar.movie_id AND ar.role_rank = 1
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    (rm.production_year = 2020 AND mk.all_keywords LIKE '%action%' OR 
    rm.production_year < 2000 AND (ar.role IS NULL OR ar.role <> 'Lead'));
