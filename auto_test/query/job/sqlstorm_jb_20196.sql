
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(c.id) OVER (PARTITION BY t.id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        cast_info c ON t.id = c.movie_id
    WHERE 
        t.production_year IS NOT NULL
        AND cn.country_code IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        rm.*,
        CTE.name
    FROM 
        RankedMovies rm
    LEFT JOIN (
        SELECT 
            ka.id AS person_id,
            ka.name
        FROM 
            aka_name ka
        WHERE 
            ka.name IS NOT NULL
            AND ka.md5sum IS NOT NULL
    ) CTE ON CTE.person_id IN (
        SELECT 
            ci.person_id 
        FROM 
            cast_info ci 
        WHERE 
            ci.movie_id = rm.movie_id
    )
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
)
SELECT 
    fm.title,
    fm.production_year,
    fm.cast_count,
    COALESCE(mk.keywords, 'No keywords') AS keywords,
    CASE 
        WHEN fm.title IS NULL THEN 'No Title'
        WHEN fm.cast_count = 0 THEN 'No Cast'
        ELSE fm.name
    END AS result_name
FROM 
    FilteredMovies fm
LEFT JOIN 
    MovieKeywords mk ON fm.movie_id = mk.movie_id
WHERE 
    fm.title_rank <= 5
GROUP BY
    fm.title,
    fm.production_year,
    fm.cast_count,
    mk.keywords,
    fm.name;
