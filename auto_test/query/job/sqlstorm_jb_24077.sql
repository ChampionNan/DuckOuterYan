
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        c.movie_id,
        ak.name AS actor_name,
        rt.role,
        CASE 
            WHEN c.nr_order IS NULL THEN 'Not Specified'
            ELSE CAST(c.nr_order AS VARCHAR)
        END AS order_specified
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    LEFT JOIN 
        role_type rt ON c.role_id = rt.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
ComplicatedQuery AS (
    SELECT 
        rt.title,
        rt.production_year,
        ar.actor_name,
        ar.role,
        COALESCE(mk.keywords, 'No Keywords') AS keywords,
        COUNT(*) OVER (PARTITION BY rt.production_year) AS total_movies_in_year,
        MAX(CASE WHEN ar.order_specified IS NOT NULL THEN ar.order_specified END) OVER (PARTITION BY rt.production_year) AS max_order_specified
    FROM 
        RankedTitles rt
    LEFT JOIN 
        ActorRoles ar ON rt.title_id = ar.movie_id
    LEFT JOIN 
        MovieKeywords mk ON rt.title_id = mk.movie_id
)
SELECT 
    c.title,
    c.production_year,
    c.actor_name,
    c.role,
    c.keywords,
    c.total_movies_in_year,
    c.max_order_specified
FROM 
    ComplicatedQuery c
WHERE 
    c.production_year >= 2000 
    AND (c.actor_name IS NOT NULL OR c.role IS NOT NULL);
