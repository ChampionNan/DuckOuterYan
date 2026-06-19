WITH RankedMovies AS (
    SELECT 
        mt.title,
        mt.production_year,
        mt.id AS movie_id,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.production_year DESC) AS year_rank,
        COUNT(ct.id) AS cast_count
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_companies mc ON mc.movie_id = mt.id
    LEFT JOIN 
        company_name cn ON cn.id = mc.company_id
    LEFT JOIN 
        movie_info mi ON mi.movie_id = mt.id
    LEFT JOIN 
        cast_info ct ON ct.movie_id = mt.id
    WHERE 
        mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Tagline')
        AND cn.country_code IS NOT NULL 
    GROUP BY 
        mt.id, mt.title, mt.production_year
),
FilteredVideos AS (
    SELECT 
        m.title,
        m.production_year,
        m.movie_id,
        m.cast_count,
        RANK() OVER (ORDER BY m.cast_count DESC) AS popular_rank
    FROM 
        RankedMovies m
    WHERE 
        m.year_rank <= 5
        AND m.cast_count > 0
),
MovieKeywords AS (
    SELECT 
        mt.title,
        k.keyword
    FROM 
        aka_title mt
    JOIN 
        movie_keyword mk ON mk.movie_id = mt.id
    JOIN 
        keyword k ON k.id = mk.keyword_id
),
CombinedResults AS (
    SELECT 
        fv.title,
        fv.production_year,
        fv.cast_count,
        COALESCE(mk.keyword, 'No Keyword') AS keyword_info,
        CASE 
            WHEN fv.cast_count > 10 THEN 'Large Cast'
            WHEN fv.cast_count BETWEEN 5 AND 10 THEN 'Medium Cast'
            ELSE 'Small Cast' 
        END AS cast_size_desc
    FROM 
        FilteredVideos fv
    LEFT JOIN 
        MovieKeywords mk ON mk.title ILIKE fv.title
)
SELECT 
    cr.title,
    cr.production_year, 
    cr.cast_count,
    cr.keyword_info,
    cr.cast_size_desc
FROM 
    CombinedResults cr
WHERE 
    cr.keyword_info IS NOT NULL
    OR cr.cast_size_desc = 'Large Cast';
