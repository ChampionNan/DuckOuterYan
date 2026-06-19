
WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS rank_within_year
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year IS NOT NULL 
        AND LOWER(k.keyword) LIKE '%action%'
),
HighRankedMovies AS (
    SELECT 
        title,
        production_year
    FROM 
        RankedMovies
    WHERE 
        rank_within_year <= 5
),
MovieCompanies AS (
    SELECT 
        m.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies m
    INNER JOIN 
        company_name c ON m.company_id = c.id
    INNER JOIN 
        company_type ct ON m.company_type_id = ct.id
    WHERE 
        c.country_code IS NOT NULL 
        AND c.country_code <> ''
),
FinalOutput AS (
    SELECT 
        h.title,
        h.production_year,
        COALESCE(mc.company_name, 'Unknown') AS company_name,
        COALESCE(mc.company_type, 'Unknown Type') AS company_type
    FROM 
        HighRankedMovies h
    LEFT JOIN 
        MovieCompanies mc ON h.production_year = (SELECT MAX(production_year) FROM HighRankedMovies)
)
SELECT 
    title,
    production_year,
    company_name,
    company_type
FROM 
    FinalOutput
WHERE 
    company_type NOT LIKE '%Producer%';
