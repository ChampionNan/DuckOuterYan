WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY c.nr_order) AS rank_order
    FROM 
        aka_title t
    JOIN 
        movie_info mi ON t.id = mi.movie_id
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.person_id
    WHERE 
        mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Genres')
        AND mi.info LIKE '%Drama%'
),
TopCast AS (
    SELECT 
        c.movie_id,
        STRING_AGG(CONCAT(n.name, ' (', r.role, ')'), ', ') AS cast_names
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        cast_info c ON mc.movie_id = c.movie_id
    JOIN 
        role_type r ON c.role_id = r.id
    JOIN 
        name n ON c.person_id = n.id
    GROUP BY 
        c.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    COALESCE(tc.cast_names, 'No cast available') AS cast_info,
    COALESCE(mi.info, 'No additional info') AS additional_info
FROM 
    RankedMovies rm
LEFT JOIN 
    movie_info mi ON rm.movie_id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Synopsis')
LEFT JOIN 
    TopCast tc ON rm.movie_id = tc.movie_id
WHERE 
    rm.rank_order <= 5;
