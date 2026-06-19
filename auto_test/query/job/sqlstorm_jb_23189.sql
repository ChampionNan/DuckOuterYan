WITH RankedMovies AS (
    SELECT 
        t.title, 
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_by_title
    FROM 
        aka_title AS t
    WHERE 
        t.production_year IS NOT NULL
),

CompanyMovieCounts AS (
    SELECT 
        mc.movie_id,
        COUNT(DISTINCT mc.company_id) AS company_count
    FROM 
        movie_companies AS mc
    WHERE 
        mc.note IS NOT NULL
    GROUP BY 
        mc.movie_id
),

DetailedMovieInfo AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        COALESCE(ki.keyword, 'No Keywords') AS keyword,
        COALESCE(cmt.kind, 'Unknown') AS company_type,
        COALESCE(rmc.company_count, 0) AS company_count
    FROM 
        aka_title AS t
    LEFT JOIN 
        movie_keyword AS mk ON mk.movie_id = t.id
    LEFT JOIN 
        keyword AS ki ON ki.id = mk.keyword_id
    LEFT JOIN 
        movie_companies AS mc ON mc.movie_id = t.id
    LEFT JOIN 
        company_type AS cmt ON cmt.id = mc.company_type_id
    LEFT JOIN 
        CompanyMovieCounts AS rmc ON rmc.movie_id = t.id
)

SELECT 
    dmi.title,
    dmi.production_year,
    dmi.keyword,
    dmi.company_type,
    dmi.company_count,
    SUM(CASE 
            WHEN dmi.company_count > 1 THEN 1 
            ELSE 0 
        END) OVER (PARTITION BY dmi.production_year) AS multi_company_movies_count,
    RANK() OVER (ORDER BY dmi.production_year, dmi.title) AS movie_rank,
    CASE 
        WHEN dmi.company_count IS NULL THEN 'No Companies'
        WHEN dmi.company_count > 5 THEN 'Many Companies'
        ELSE 'Few Companies' 
    END AS company_classification
FROM 
    DetailedMovieInfo AS dmi
WHERE 
    dmi.production_year >= 2000
    AND (dmi.keyword IS NULL OR dmi.keyword NOT LIKE '%Documentary%');
