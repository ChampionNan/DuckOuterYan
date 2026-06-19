WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        COALESCE(ka.name, 'Unknown') AS director_name,
        COUNT(c.id) OVER (PARTITION BY t.id) AS cast_count,
        ROW_NUMBER() OVER (ORDER BY t.production_year DESC, t.title) AS rank
    FROM 
        aka_title AS t
    LEFT JOIN 
        movie_companies AS mc ON mc.movie_id = t.movie_id
    LEFT JOIN 
        company_name AS cn ON cn.id = mc.company_id 
        AND cn.country_code IS NOT NULL
    LEFT JOIN 
        cast_info AS c ON c.movie_id = t.movie_id
    LEFT JOIN 
        aka_name AS ka ON ka.person_id = c.person_id 
        AND ka.name IS NOT NULL
    WHERE 
        t.production_year IS NOT NULL AND 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE '%Drama%')
),
FilteredMovies AS (
    SELECT 
        R.*,
        CASE 
            WHEN director_name IS NULL THEN 'No Director Found'
            WHEN cast_count = 0 THEN 'No Cast Found'
            ELSE 'Valid Movie'
        END AS status
    FROM 
        RankedMovies AS R
    WHERE 
        rank <= 10
),
FinalOutput AS (
    SELECT 
        movie_id,
        title,
        production_year,
        director_name,
        cast_count,
        status,
        RANK() OVER (PARTITION BY production_year ORDER BY cast_count DESC) AS yearly_cast_rank
    FROM 
        FilteredMovies
)

SELECT 
    f.movie_id,
    f.title,
    f.production_year,
    f.director_name,
    f.cast_count,
    f.status,
    f.yearly_cast_rank,
    CASE 
        WHEN f.yearly_cast_rank IS NOT NULL AND f.yearly_cast_rank <= 3 THEN 'Top 3 Cast'
        ELSE 'Other'
    END AS cast_ranking
FROM 
    FinalOutput AS f
LEFT JOIN 
    movie_info AS mi ON mi.movie_id = f.movie_id 
    AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Budget')
WHERE 
    f.status <> 'No Cast Found';
