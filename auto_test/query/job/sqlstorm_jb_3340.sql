WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        RANK() OVER (PARTITION BY m.production_year ORDER BY m.title) AS title_rank
    FROM 
        aka_title m
    WHERE 
        m.production_year IS NOT NULL
),
CompanyInfo AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS company_rank
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
FullMovieInfo AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        ci.company_name,
        ci.company_type,
        mk.keywords,
        CASE 
            WHEN mk.keywords IS NULL THEN 'No Keywords'
            ELSE mk.keywords
        END AS keywords_display
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CompanyInfo ci ON rm.movie_id = ci.movie_id
    LEFT JOIN 
        MovieKeywords mk ON rm.movie_id = mk.movie_id
)
SELECT 
    f.movie_id,
    f.title,
    f.production_year,
    COALESCE(f.company_name, 'Independent') AS company_name,
    f.company_type,
    f.keywords_display
FROM 
    FullMovieInfo f
WHERE 
    f.production_year >= 2000
    AND f.keywords_display LIKE '%Drama%';
