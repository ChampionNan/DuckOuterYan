
WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        RANK() OVER (ORDER BY t.production_year DESC) AS rank_order
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword LIKE '%action%'
),
ActorMovies AS (
    SELECT 
        c.movie_id,
        a.name,
        a.id AS actor_id
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    WHERE 
        a.name IS NOT NULL
),
MovieCompanies AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        co.kind AS company_type
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        company_type co ON mc.company_type_id = co.id
)
SELECT 
    rm.title,
    rm.production_year,
    am.name AS actor_name,
    COALESCE(mc.company_name, 'Unknown') AS company_name,
    COALESCE(mc.company_type, 'Independent') AS company_type,
    COUNT(am.movie_id) OVER (PARTITION BY am.actor_id) AS total_movies
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorMovies am ON rm.title_id = am.movie_id
LEFT JOIN 
    MovieCompanies mc ON rm.title_id = mc.movie_id
WHERE 
    rm.rank_order <= 10;
