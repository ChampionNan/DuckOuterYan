WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY t.production_year DESC) AS rn
    FROM 
        title t
    JOIN 
        cast_info ci ON t.id = ci.movie_id
    JOIN 
        role_type r ON ci.role_id = r.id
    WHERE 
        t.production_year > 2000
),
TopMovies AS (
    SELECT 
        movie_id,
        title
    FROM 
        RankedMovies
    WHERE 
        rn = 1
),
CompanyMovie AS (
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
        tm.title,
        cm.company_name,
        cm.company_type,
        COUNT(DISTINCT km.keyword_id) AS keyword_count
    FROM 
        TopMovies tm
    LEFT JOIN 
        CompanyMovie cm ON tm.movie_id = cm.movie_id
    LEFT JOIN 
        movie_keyword km ON tm.movie_id = km.movie_id
    GROUP BY 
        tm.title, cm.company_name, cm.company_type
),
FinalResults AS (
    SELECT 
        title,
        company_name,
        company_type,
        keyword_count,
        CASE 
            WHEN keyword_count IS NULL THEN 'No Keywords'
            WHEN keyword_count = 0 THEN 'No Keywords'
            ELSE cast(keyword_count AS text) || ' Keywords'
        END AS keyword_info
    FROM 
        MovieDetails
)
SELECT 
    fr.title,
    fr.company_name,
    fr.company_type,
    fr.keyword_count,
    fr.keyword_info
FROM 
    FinalResults fr
WHERE 
    fr.company_type IS NOT NULL;
