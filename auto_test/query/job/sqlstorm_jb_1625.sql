WITH MovieDetails AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        COALESCE(k.keyword, 'No Keyword') AS keyword,
        COUNT(ci.person_id) AS cast_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON a.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    GROUP BY 
        a.id, a.title, a.production_year, k.keyword
),
RankedMovies AS (
    SELECT 
        md.movie_id,
        md.title,
        md.production_year,
        md.keyword,
        md.cast_count,
        RANK() OVER (PARTITION BY md.keyword ORDER BY md.cast_count DESC) AS rank_within_keyword
    FROM 
        MovieDetails md
)
SELECT 
    rm.title,
    rm.production_year,
    rm.keyword,
    rm.cast_count,
    CASE 
        WHEN rm.rank_within_keyword <= 3 THEN 'Top Cast'
        ELSE 'Other' 
    END AS rank_category
FROM 
    RankedMovies rm
WHERE 
    rm.production_year >= 2000 
    AND EXISTS (
        SELECT 1 
        FROM movie_info mi 
        WHERE mi.movie_id = rm.movie_id 
        AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Box Office')
        AND mi.info IS NOT NULL
    );
