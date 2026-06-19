WITH Recursive ActorHierarchy AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        c.movie_id,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY c.nr_order) AS rn
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    LEFT JOIN 
        movie_companies mc ON c.movie_id = mc.movie_id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        a.name IS NOT NULL AND
        c.nr_order IS NOT NULL
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
ActorMovies AS (
    SELECT 
        ah.actor_name,
        ah.movie_id,
        ROW_NUMBER() OVER (PARTITION BY ah.actor_id ORDER BY ah.movie_id) AS movie_rank,
        COALESCE(mk.keywords, 'None') AS movie_keywords
    FROM 
        ActorHierarchy ah
    LEFT JOIN 
        MovieKeywords mk ON ah.movie_id = mk.movie_id
),
FilteredActors AS (
    SELECT 
        DISTINCT actor_name,
        movie_id,
        movie_keywords
    FROM 
        ActorMovies
    WHERE 
        movie_rank <= 10
),
FinalOutput AS (
    SELECT 
        f.actor_name,
        f.movie_id,
        COALESCE(f.movie_keywords, 'No Keywords Found') AS keywords,
        COUNT(f.movie_id) OVER (PARTITION BY f.actor_name) AS movie_count
    FROM 
        FilteredActors f
)
SELECT 
    fo.actor_name,
    fo.movie_id,
    fo.keywords,
    fo.movie_count,
    CASE 
        WHEN fo.movie_count > 5 THEN 'Prolific Actor'
        ELSE 'Emerging Talent'
    END AS actor_status
FROM 
    FinalOutput fo
WHERE 
    fo.keywords NOT LIKE '%Action%';
