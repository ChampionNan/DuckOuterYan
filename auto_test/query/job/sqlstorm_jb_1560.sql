WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        COUNT(*) OVER (PARTITION BY c.movie_id) AS role_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieKeywords AS (
    SELECT 
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword m
    JOIN 
        keyword k ON m.keyword_id = k.id
    GROUP BY 
        m.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    ak.actor_name,
    ak.role_name,
    mk.keywords,
    COALESCE(ak.role_count, 0) AS total_roles,
    CASE 
        WHEN rm.production_year < 2000 THEN 'Before 2000'
        WHEN rm.production_year BETWEEN 2000 AND 2010 THEN '2000-2010'
        ELSE 'After 2010'
    END AS period
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorRoles ak ON rm.movie_id = ak.movie_id
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    (rm.title ILIKE '%star%' OR rm.production_year >= 2021);
