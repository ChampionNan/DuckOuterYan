WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_year
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
MovieWithKeywords AS (
    SELECT 
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        (SELECT DISTINCT movie_id FROM movie_info) m ON mk.movie_id = m.movie_id
    GROUP BY 
        m.movie_id
),
FullMovieInfo AS (
    SELECT 
        m.movie_id,
        m.title,
        m.production_year,
        COALESCE(kw.keywords, 'No keywords') AS keywords,
        COALESCE(c.name, 'Unknown') AS company,
        COALESCE(a.name, 'Unknown') AS actor
    FROM 
        RankedMovies m
    LEFT JOIN 
        movie_companies mc ON m.movie_id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    LEFT JOIN 
        cast_info ci ON m.movie_id = ci.movie_id
    LEFT JOIN 
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN 
        MovieWithKeywords kw ON m.movie_id = kw.movie_id
    WHERE 
        m.rank_year <= 5
)
SELECT 
    f.title,
    f.production_year,
    f.keywords,
    f.company,
    f.actor
FROM 
    FullMovieInfo f
WHERE 
    f.production_year BETWEEN 2000 AND 2020;
