
WITH RankedMovies AS (
    SELECT 
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC, at.title) AS rank
    FROM 
        aka_title at
    WHERE 
        at.production_year IS NOT NULL
),
FilteredCast AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        cast_info ci
    WHERE 
        ci.note IS NULL  
    GROUP BY 
        ci.movie_id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_kind
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        c.country_code IS NOT NULL
),
DetailedMovieInfo AS (
    SELECT 
        rm.title,
        rm.production_year,
        COALESCE(fc.actor_count, 0) AS actor_count,
        cd.company_name,
        cd.company_kind
    FROM 
        RankedMovies rm
    LEFT JOIN 
        FilteredCast fc ON rm.title = (SELECT title FROM aka_title WHERE movie_id = fc.movie_id LIMIT 1) 
    LEFT JOIN 
        CompanyDetails cd ON rm.title = (SELECT title FROM aka_title WHERE movie_id = cd.movie_id LIMIT 1)
)
SELECT 
    d.title,
    d.production_year,
    d.actor_count,
    d.company_name,
    d.company_kind
FROM 
    DetailedMovieInfo d
WHERE 
    d.production_year > 2000 
    AND (d.actor_count >= 5 OR d.company_kind = 'Distributor');
