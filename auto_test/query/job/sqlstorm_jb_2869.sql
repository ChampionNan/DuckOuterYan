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
        AND t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie')
),
DirectorInfo AS (
    SELECT 
        c.movie_id,
        a.name AS director_name,
        c.nr_order
    FROM 
        cast_info c
    INNER JOIN 
        aka_name a ON a.person_id = c.person_id
    WHERE 
        c.role_id = (SELECT id FROM role_type WHERE role = 'director')
),
TitleKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
MoviesWithKeywords AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(tk.keywords, 'No keywords') AS keywords
    FROM 
        RankedMovies rm
    LEFT JOIN 
        TitleKeywords tk ON rm.movie_id = tk.movie_id
)
SELECT 
    mwk.movie_id,
    mwk.title,
    mwk.production_year,
    di.director_name,
    mwk.keywords,
    CASE 
        WHEN mwk.production_year >= 2000 THEN 'Modern Era'
        WHEN mwk.production_year IS NULL THEN 'Unknown Year'
        ELSE 'Classic Era'
    END AS era_category
FROM 
    MoviesWithKeywords mwk
LEFT JOIN 
    DirectorInfo di ON mwk.movie_id = di.movie_id
WHERE 
    mwk.keywords IS NOT NULL
    AND mwk.production_year BETWEEN 1990 AND 2023;
