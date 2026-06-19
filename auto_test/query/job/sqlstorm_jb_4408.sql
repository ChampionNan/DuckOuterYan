WITH MovieDetails AS (
    SELECT 
        t.title, 
        t.production_year, 
        c.name AS company_name,
        COUNT(ci.person_id) AS total_cast,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY t.production_year DESC) AS rn
    FROM 
        aka_title t
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id AND c.country_code IS NOT NULL
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    GROUP BY 
        t.id, t.title, t.production_year, c.name
),
TopMovies AS (
    SELECT 
        title, 
        production_year, 
        company_name, 
        total_cast
    FROM 
        MovieDetails
    WHERE 
        rn = 1 AND total_cast > 5
),
MovieKeywords AS (
    SELECT 
        t.title,
        k.keyword
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
)
SELECT 
    tm.title,
    tm.production_year,
    COALESCE(tm.company_name, 'Unknown') AS company,
    k.keyword AS movie_keyword
FROM 
    TopMovies tm
FULL OUTER JOIN 
    MovieKeywords k ON tm.title = k.title
WHERE 
    tm.production_year >= 2000;
