WITH MovieDetails AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        COALESCE(NULLIF(k.keyword, ''), 'N/A') AS keyword,
        COALESCE(NULLIF(c_type.kind, 'none'), 'Unknown') AS company_type,
        COUNT(DISTINCT c.person_id) AS cast_count
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_type c_type ON mc.company_type_id = c_type.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.id
    GROUP BY 
        t.id, t.title, t.production_year, k.keyword, c_type.kind
),
RankedMovies AS (
    SELECT 
        md.*, 
        RANK() OVER (PARTITION BY md.production_year ORDER BY md.cast_count DESC) AS rn
    FROM 
        MovieDetails md
)
SELECT 
    rm.movie_id, 
    rm.title, 
    rm.production_year, 
    rm.keyword, 
    rm.company_type, 
    rm.cast_count
FROM 
    RankedMovies rm
WHERE 
    rm.rn <= 3
    AND (rm.production_year IS NOT NULL OR rm.keyword IS NOT NULL);
