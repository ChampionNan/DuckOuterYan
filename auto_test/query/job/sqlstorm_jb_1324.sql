WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id, 
        a.title AS movie_title, 
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS rank_year
    FROM 
        aka_title a
    WHERE 
        a.kind_id = 1 
), 
ActorRoles AS (
    SELECT 
        ci.movie_id, 
        ak.name AS actor_name, 
        rt.role AS role_name, 
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS total_actors
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        role_type rt ON ci.person_role_id = rt.id
), 
MoviesWithCompanies AS (
    SELECT 
        rm.movie_id,
        rm.movie_title,
        STRING_AGG(DISTINCT cn.name, ', ') AS production_companies
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_companies mc ON rm.movie_id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    GROUP BY 
        rm.movie_id, rm.movie_title
)
SELECT 
    m.movie_id, 
    m.movie_title, 
    m.production_year,
    ar.actor_name,
    ar.role_name,
    COALESCE(mw.production_companies, 'No Companies') AS production_companies,
    ar.total_actors
FROM 
    ActorRoles ar
JOIN 
    MoviesWithCompanies mw ON ar.movie_id = mw.movie_id
JOIN 
    RankedMovies m ON mw.movie_id = m.movie_id
WHERE 
    m.rank_year <= 5;
