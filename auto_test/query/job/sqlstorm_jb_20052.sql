
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(ci.person_id) OVER (PARTITION BY t.id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        cast_info ci ON t.id = ci.movie_id
    LEFT JOIN 
        aka_name an ON ci.person_id = an.person_id
    LEFT JOIN 
        name nm ON an.person_id = nm.imdb_id
    LEFT JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        t.production_year IS NOT NULL
        AND cn.country_code IS NOT NULL
),

MovieKeywordDetails AS (
    SELECT 
        mk.movie_id,
        ARRAY_AGG(DISTINCT k.keyword) AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)

SELECT 
    rm.title,
    rm.production_year,
    rm.title_rank,
    COALESCE(mkd.keywords, ARRAY[]::text[]) AS keywords,
    rm.cast_count,
    CASE 
        WHEN rm.cast_count > 5 THEN 'Large Cast'
        WHEN rm.cast_count BETWEEN 3 AND 5 THEN 'Medium Cast'
        ELSE 'Small Cast'
    END AS cast_size,
    NULLIF(rt.role, 'Unknown') AS role
FROM 
    RankedMovies rm
LEFT JOIN 
    movie_info mi ON rm.movie_id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Plot')
LEFT JOIN 
    MovieKeywordDetails mkd ON rm.movie_id = mkd.movie_id
LEFT JOIN 
    cast_info ci ON rm.movie_id = ci.movie_id
LEFT JOIN 
    role_type rt ON ci.role_id = rt.id
WHERE 
    (MOD(rm.production_year, 2) <> 0 OR mi.info IS NULL) 
    AND (rm.production_year BETWEEN 1980 AND 2023);
