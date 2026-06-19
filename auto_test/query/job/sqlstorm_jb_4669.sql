
WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year, 
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.production_year DESC) AS rank
    FROM 
        aka_title m
    WHERE 
        m.production_year IS NOT NULL
),
ActorMovies AS (
    SELECT 
        a.name AS actor_name, 
        at.title AS movie_title, 
        at.production_year, 
        RANK() OVER (PARTITION BY a.id ORDER BY at.production_year DESC) AS actor_rank,
        at.id AS movie_id
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        aka_title at ON c.movie_id = at.id
    WHERE 
        a.name IS NOT NULL
),
CompanyDetails AS (
    SELECT 
        cm.id AS company_id, 
        cm.name AS company_name, 
        ct.kind AS company_type
    FROM 
        company_name cm
    LEFT JOIN 
        company_type ct ON cm.id = ct.id 
    WHERE 
        cm.country_code = 'USA'
),
MovieKeywords AS (
    SELECT 
        mk.movie_id, 
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.rank, 
    rm.title, 
    rm.production_year, 
    am.actor_name, 
    cd.company_name, 
    wd.keywords
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorMovies am ON rm.movie_id = am.movie_id
LEFT JOIN 
    movie_companies mc ON rm.movie_id = mc.movie_id
LEFT JOIN 
    CompanyDetails cd ON mc.company_id = cd.company_id
LEFT JOIN 
    MovieKeywords wd ON rm.movie_id = wd.movie_id
WHERE 
    rm.rank <= 5 
    AND (cd.company_type IS NULL OR cd.company_type = 'Producer')
    AND wd.keywords IS NOT NULL;
