WITH RankedMovies AS (
    SELECT 
        t.title,
        t.production_year,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2023
    GROUP BY 
        t.id, t.title, t.production_year
),
TopRatedMovies AS (
    SELECT 
        rm.title,
        rm.production_year,
        rm.cast_count,
        ROW_NUMBER() OVER (ORDER BY rm.cast_count DESC) AS rank
    FROM 
        RankedMovies rm
)
SELECT 
    trm.title,
    trm.production_year,
    trm.cast_count,
    p.info AS director_info
FROM 
    TopRatedMovies trm
LEFT JOIN 
    movie_info mi ON trm.title = mi.info
LEFT JOIN 
    person_info p ON mi.movie_id = p.person_id
WHERE 
    trm.rank <= 10
    AND p.info_type_id = (SELECT id FROM info_type WHERE info = 'Director');
