WITH RankedMovies AS (
    SELECT 
        a.title AS movie_title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS title_rank,
        COALESCE(b.name, 'Unknown') AS company_name,
        COUNT(DISTINCT c.person_id) AS cast_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_companies mc ON a.id = mc.movie_id
    LEFT JOIN 
        company_name b ON mc.company_id = b.id
    LEFT JOIN 
        complete_cast cc ON a.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.person_id
    WHERE 
        a.production_year BETWEEN 1990 AND 2020
    GROUP BY 
        a.title, a.production_year, b.name
),
TopMovies AS (
    SELECT 
        movie_title, 
        production_year, 
        title_rank, 
        company_name, 
        cast_count,
        AVG(cast_count) OVER (PARTITION BY production_year) AS avg_cast_count,
        (cast_count - AVG(cast_count) OVER (PARTITION BY production_year)) AS cast_count_diff
    FROM 
        RankedMovies
)
SELECT 
    movie_title,
    production_year,
    company_name,
    CASE 
        WHEN cast_count > avg_cast_count THEN 'Above Average' 
        WHEN cast_count < avg_cast_count THEN 'Below Average' 
        ELSE 'Average' 
    END AS cast_performance,
    cast_count,
    cast_count_diff
FROM 
    TopMovies
WHERE 
    title_rank <= 5;
