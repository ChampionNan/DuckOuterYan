
WITH RankedMovies AS (
    SELECT 
        a.title AS movie_title,
        a.production_year,
        ci.note AS cast_note,
        COUNT(DISTINCT k.keyword) AS keyword_count,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS rn
    FROM 
        aka_title a
    JOIN 
        complete_cast cc ON a.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_info mi ON a.id = mi.movie_id
    LEFT JOIN 
        info_type it ON mi.info_type_id = it.id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        a.production_year > 2000
    GROUP BY 
        a.id, a.title, a.production_year, ci.note
)
SELECT 
    rm.movie_title,
    rm.production_year,
    rm.cast_note,
    rm.keyword_count
FROM 
    RankedMovies rm
WHERE 
    rm.rn = 1;
