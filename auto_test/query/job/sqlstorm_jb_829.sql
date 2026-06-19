WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie')
),
TopMovies AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year, 
        c.name AS company_name
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_companies mc ON rm.movie_id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    WHERE 
        rm.title_rank <= 5
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
FinalResults AS (
    SELECT 
        tm.movie_id, 
        tm.title, 
        tm.production_year, 
        COALESCE(tk.keywords, 'No keywords') AS keywords,
        CASE 
            WHEN tm.company_name IS NULL THEN 'Independent'
            ELSE tm.company_name
        END AS company_type
    FROM 
        TopMovies tm
    LEFT JOIN 
        MovieKeywords tk ON tm.movie_id = tk.movie_id
)
SELECT 
    fr.movie_id, 
    fr.title, 
    fr.production_year, 
    fr.keywords, 
    fr.company_type
FROM 
    FinalResults fr
WHERE 
    fr.production_year >= 2000;
