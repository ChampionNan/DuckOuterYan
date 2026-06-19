WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        a.kind_id,
        m.name AS company_name,
        k.keyword AS genre,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS rank_within_year
    FROM 
        aka_title a
    JOIN 
        movie_companies mc ON a.movie_id = mc.movie_id
    JOIN 
        company_name m ON mc.company_id = m.id
    JOIN 
        movie_keyword mk ON a.movie_id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year IS NOT NULL AND
        m.country_code = 'USA'
),
Synopsis AS (
    SELECT 
        m.movie_id,
        STRING_AGG(DISTINCT i.info, ', ') AS synopsis_info
    FROM 
        RankedMovies m
    LEFT JOIN 
        movie_info i ON m.movie_id = i.movie_id
    GROUP BY 
        m.movie_id
)
SELECT 
    rm.title,
    rm.production_year,
    rm.company_name,
    rm.genre,
    s.synopsis_info
FROM 
    RankedMovies rm
LEFT JOIN 
    Synopsis s ON rm.movie_id = s.movie_id
WHERE 
    rm.rank_within_year <= 5;
