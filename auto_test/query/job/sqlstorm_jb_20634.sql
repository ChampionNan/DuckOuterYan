WITH RankedMovies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        RANK() OVER (PARTITION BY mt.production_year ORDER BY mt.production_year DESC, mt.title) AS year_rank
    FROM 
        aka_title mt
    WHERE 
        mt.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie') 
        AND mt.production_year > 2000
),
CastInfoWithRole AS (
    SELECT 
        ci.id,
        ci.movie_id,
        ci.person_id,
        ci.role_id,
        cr.role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_order
    FROM 
        cast_info ci
    LEFT JOIN 
        role_type cr ON ci.role_id = cr.id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        COUNT(*) OVER (PARTITION BY mc.movie_id) AS total_companies
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        c.country_code IS NOT NULL
),
KeywordDetails AS (
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
FinalOutput AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        cwr.person_id,
        cwr.role,
        cwr.role_order,
        cd.company_name,
        cd.company_type,
        cd.total_companies,
        kd.keywords
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CastInfoWithRole cwr ON rm.movie_id = cwr.movie_id
    LEFT JOIN 
        CompanyDetails cd ON rm.movie_id = cd.movie_id
    LEFT JOIN 
        KeywordDetails kd ON rm.movie_id = kd.movie_id
)
SELECT 
    movie_id,
    title,
    production_year,
    person_id,
    COALESCE(role, 'Unknown Role') AS role,
    role_order,
    COALESCE(company_name, 'Independent') AS company_name,
    company_type,
    total_companies,
    COALESCE(keywords, 'No Keywords') AS keywords
FROM 
    FinalOutput
WHERE 
    production_year IS NOT NULL
    AND (keywords IS NULL OR keywords LIKE '%Action%');
