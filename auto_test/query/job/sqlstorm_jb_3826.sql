
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorMovies AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        c.movie_id,
        r.role AS character_name
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
FilteredCompanies AS (
    SELECT 
        mc.movie_id,
        company.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name company ON mc.company_id = company.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        company.country_code IS NOT NULL
),
MoviesWithKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)

SELECT 
    rm.title,
    rm.production_year,
    am.actor_name,
    fm.company_name,
    fm.company_type,
    COALESCE(mw.keywords, 'No Keywords') AS keywords,
    CASE 
        WHEN rm.title_rank <= 3 THEN 'Top Movie'
        ELSE 'Other'
    END AS movie_rank_category
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorMovies am ON rm.movie_id = am.movie_id
LEFT JOIN 
    FilteredCompanies fm ON rm.movie_id = fm.movie_id
LEFT JOIN 
    MoviesWithKeywords mw ON rm.movie_id = mw.movie_id
WHERE 
    rm.production_year >= 2000
    AND (am.actor_name IS NOT NULL OR fm.company_name IS NOT NULL)
GROUP BY 
    rm.title,
    rm.production_year,
    am.actor_name,
    fm.company_name,
    fm.company_type,
    mw.keywords,
    rm.title_rank;
