
WITH RankedMovies AS (
    SELECT 
        m.title,
        m.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY m.production_year DESC) AS rn,
        m.id
    FROM 
        aka_title m
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        m.production_year IS NOT NULL
), MovieRatings AS (
    SELECT 
        c.movie_id,
        AVG(CAST(pi.info AS FLOAT)) AS avg_rating
    FROM 
        complete_cast c
    JOIN 
        person_info pi ON c.subject_id = pi.person_id 
    WHERE 
        pi.info_type_id = (SELECT id FROM info_type WHERE info = 'Rating')
    GROUP BY 
        c.movie_id
), FilteredMovies AS (
    SELECT 
        rm.title,
        rm.production_year,
        rm.keyword,
        COALESCE(mr.avg_rating, 0) AS avg_rating 
    FROM 
        RankedMovies rm
    LEFT JOIN 
        MovieRatings mr ON rm.id = mr.movie_id
    WHERE 
        rm.rn = 1
)
SELECT 
    f.title,
    f.production_year,
    f.keyword,
    f.avg_rating,
    CASE 
        WHEN f.avg_rating IS NULL THEN 'No Ratings'
        WHEN f.avg_rating >= 8 THEN 'Highly Rated'
        WHEN f.avg_rating >= 5 THEN 'Moderately Rated'
        ELSE 'Low Rated'
    END AS rating_category
FROM 
    FilteredMovies f
WHERE 
    f.production_year >= 2000;
