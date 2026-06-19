WITH RankedMovies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.title) AS title_rank
    FROM 
        aka_title mt
    WHERE 
        mt.kind_id IN (SELECT id FROM kind_type WHERE kind ILIKE '%feature%') 
        AND mt.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        ci.movie_id,
        cn.name AS actor_name,
        rt.role AS actor_role,
        COUNT(*) OVER (PARTITION BY ci.movie_id, rt.role) AS role_count
    FROM 
        cast_info ci
    JOIN 
        name cn ON ci.person_id = cn.imdb_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords_list
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.movie_title,
    COALESCE(ak.actor_name, 'Unknown Actor') AS actor_name,
    ak.actor_role,
    ak.role_count,
    COALESCE(mk.keywords_list, 'No keywords') AS keywords,
    CASE 
        WHEN rm.production_year < 2000 THEN 'Classic'
        WHEN rm.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS era
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorRoles ak ON rm.movie_id = ak.movie_id AND ak.role_count = 1 
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    rm.title_rank <= 5;
