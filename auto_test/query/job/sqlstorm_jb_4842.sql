WITH RankedMovies AS (
    SELECT 
        at.id AS title_id,
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC) AS rn
    FROM 
        aka_title at
    WHERE 
        at.production_year IS NOT NULL
),
TopCast AS (
    SELECT 
        ci.movie_id,
        ak.name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS cast_order
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        ak.name IS NOT NULL
),
MoviesWithKeywords AS (
    SELECT 
        mt.movie_id,
        STRING_AGG(mk.keyword, ', ') AS keywords
    FROM 
        movie_keyword mt
    JOIN 
        keyword mk ON mt.keyword_id = mk.id
    GROUP BY 
        mt.movie_id
)
SELECT 
    rm.title_id,
    rm.title,
    rm.production_year,
    tc.name AS top_cast,
    mwk.keywords,
    CASE 
        WHEN tc.cast_order <= 5 THEN 'Top Cast'
        ELSE 'Supporting Cast'
    END AS cast_category
FROM 
    RankedMovies rm
LEFT JOIN 
    TopCast tc ON rm.title_id = tc.movie_id
LEFT JOIN 
    MoviesWithKeywords mwk ON rm.title_id = mwk.movie_id
WHERE 
    rm.rn <= 10
