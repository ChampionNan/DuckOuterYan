WITH ActorMovies AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        r.role AS role_type
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        title t ON ci.movie_id = t.id
    JOIN 
        role_type r ON ci.role_id = r.id
),
CompanyInfo AS (
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
CompleteMovieInfo AS (
    SELECT 
        a.actor_id,
        a.actor_name,
        a.movie_title,
        a.production_year,
        a.role_type,
        ci.company_name,
        ci.company_type,
        mk.keywords
    FROM 
        ActorMovies a
    LEFT JOIN 
        CompanyInfo ci ON a.production_year = ci.movie_id
    LEFT JOIN 
        MovieKeywords mk ON a.production_year = mk.movie_id
)
SELECT 
    actor_name,
    movie_title,
    production_year,
    role_type,
    company_name,
    company_type,
    keywords
FROM 
    CompleteMovieInfo
WHERE 
    production_year BETWEEN 2000 AND 2020;
