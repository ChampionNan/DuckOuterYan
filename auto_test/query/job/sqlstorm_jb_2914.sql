
WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        RANK() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank,
        COUNT(DISTINCT c.person_id) AS cast_count
    FROM 
        aka_title a
    JOIN 
        complete_cast cc ON a.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.id
    WHERE 
        a.production_year IS NOT NULL
    GROUP BY 
        a.title, a.production_year
),
MovieDetails AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        COALESCE(g.kind, 'Unknown') AS genre,
        COALESCE(k.keyword, 'None') AS keyword,
        COALESCE(mo.info, 'No Info') AS additional_info,
        m.production_year
    FROM 
        title m
    LEFT JOIN 
        kind_type g ON m.kind_id = g.id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_info mo ON m.id = mo.movie_id
    WHERE 
        m.production_year >= 2000
)
SELECT 
    md.title,
    md.production_year,
    md.genre,
    md.keyword,
    rm.cast_count
FROM 
    MovieDetails md
JOIN 
    RankedMovies rm ON md.title = rm.title AND md.production_year = rm.production_year
WHERE 
    (rm.year_rank <= 10 OR rm.cast_count > 5);
