
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS level,
        NULL AS parent_id
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL  
    
    UNION ALL
    
    SELECT 
        at.id AS movie_id,
        at.title,
        at.production_year,
        mh.level + 1,
        mh.movie_id AS parent_id
    FROM 
        aka_title at
    JOIN 
        MovieHierarchy mh ON at.episode_of_id = mh.movie_id
),
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
MovieDetails AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        cm.company_name,
        cm.company_type,
        ROW_NUMBER() OVER (PARTITION BY mh.movie_id ORDER BY cm.company_type) AS company_rank
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        CompanyMovies cm ON mh.movie_id = cm.movie_id
),
ActorMovies AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        COUNT(ci.id) AS role_count
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    GROUP BY 
        ci.movie_id, a.name
),
FinalBenchmark AS (
    SELECT 
        md.movie_id,
        md.title,
        md.production_year,
        md.company_name,
        md.company_type,
        COALESCE(am.actor_name, 'No Actors') AS actor_name,
        COALESCE(am.role_count, 0) AS role_count,
        md.company_rank
    FROM 
        MovieDetails md
    LEFT JOIN 
        ActorMovies am ON md.movie_id = am.movie_id
)
SELECT 
    fb.*,
    RANK() OVER (PARTITION BY fb.title ORDER BY fb.production_year DESC) AS production_rank,
    CASE 
        WHEN fb.role_count > 0 THEN 'Has Actors'
        ELSE 'No Actors'
    END AS actor_presence
FROM 
    FinalBenchmark fb
WHERE 
    fb.production_year = 2022;
