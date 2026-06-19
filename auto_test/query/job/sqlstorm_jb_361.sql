WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
KeywordCounts AS (
    SELECT 
        mk.movie_id,
        COUNT(DISTINCT k.keyword) AS keyword_count
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
TopMovies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        cd.company_name,
        cd.company_type,
        COALESCE(kc.keyword_count, 0) AS keyword_count
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CompanyDetails cd ON rm.movie_id = cd.movie_id
    LEFT JOIN 
        KeywordCounts kc ON rm.movie_id = kc.movie_id
    WHERE
        rm.year_rank <= 5
)
SELECT 
    title,
    production_year,
    company_name,
    company_type,
    keyword_count,
    CASE 
        WHEN keyword_count > 5 THEN 'Highly Tagged'
        WHEN keyword_count BETWEEN 1 AND 5 THEN 'Moderately Tagged'
        ELSE 'Not Tagged'
    END AS tagging_status
FROM 
    TopMovies
WHERE 
    company_type IS NOT NULL;
