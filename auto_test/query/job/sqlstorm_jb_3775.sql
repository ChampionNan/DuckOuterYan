WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn,
        COUNT(c.id) OVER (PARTITION BY t.id) AS total_cast
    FROM 
        aka_title t
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.person_id
    WHERE 
        t.production_year IS NOT NULL
),
FilteredTitles AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        rm.rn,
        rm.total_cast
    FROM 
        RankedMovies rm
    WHERE 
        rm.total_cast > 3
),
TitleKeywords AS (
    SELECT 
        mt.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mt
    JOIN 
        keyword k ON mt.keyword_id = k.id
    GROUP BY 
        mt.movie_id
)
SELECT 
    ft.title,
    ft.production_year,
    ft.total_cast,
    COALESCE(tk.keywords, 'No Keywords') AS keywords
FROM 
    FilteredTitles ft
LEFT JOIN 
    TitleKeywords tk ON ft.movie_id = tk.movie_id
WHERE 
    ft.production_year > 2000;
