WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
),
ActorRoles AS (
    SELECT 
        c.person_id,
        c.movie_id,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY c.person_id ORDER BY c.nr_order) AS role_rank
    FROM 
        cast_info c
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY mk.movie_id ORDER BY k.keyword) AS keyword_rank
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
MovieInfo AS (
    SELECT 
        mi.movie_id,
        STRING_AGG(mi.info, '; ') AS aggregated_info
    FROM 
        movie_info mi
    GROUP BY 
        mi.movie_id
)

SELECT DISTINCT 
    a.name AS actor_name,
    rt.title AS movie_title,
    rt.production_year,
    ar.role,
    mk.keyword,
    mi.aggregated_info
FROM 
    aka_name a
JOIN 
    ActorRoles ar ON a.person_id = ar.person_id
JOIN 
    RankedTitles rt ON ar.movie_id = rt.title_id AND rt.title_rank = 1
LEFT JOIN 
    MovieKeywords mk ON ar.movie_id = mk.movie_id AND mk.keyword_rank = 1
LEFT JOIN 
    MovieInfo mi ON ar.movie_id = mi.movie_id
WHERE 
    a.name IS NOT NULL;
