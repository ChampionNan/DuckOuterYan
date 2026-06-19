
WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_by_year
    FROM 
        aka_title t
    JOIN 
        aka_name a ON a.id = t.id
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        c.movie_id,
        c.person_id,
        rt.role,
        COUNT(*) OVER (PARTITION BY c.person_id) AS role_count
    FROM 
        cast_info c
    JOIN 
        role_type rt ON c.role_id = rt.id
),
MoviesWithKeywords AS (
    SELECT 
        m.id AS movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
    INNER JOIN 
        aka_title m ON mk.movie_id = m.id
    GROUP BY 
        m.id
),
FinalResults AS (
    SELECT 
        r.title,
        r.production_year,
        a.name AS actor_name,
        ar.role,
        mwk.keywords,
        COALESCE(ar.role_count, 0) AS role_count
    FROM 
        RankedTitles r
    LEFT JOIN 
        ActorRoles ar ON r.aka_id = ar.person_id
    LEFT JOIN 
        aka_name a ON a.id = ar.person_id
    LEFT JOIN 
        MoviesWithKeywords mwk ON r.aka_id = mwk.movie_id
    WHERE 
        r.rank_by_year = 1
)

SELECT
    title,
    production_year,
    COALESCE(actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(role, 'No Role Assigned') AS role,
    COALESCE(keywords, 'No Keywords') AS keywords,
    role_count
FROM 
    FinalResults;
