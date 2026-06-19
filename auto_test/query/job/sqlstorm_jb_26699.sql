
WITH RankedMovies AS (
    SELECT 
        t.title,
        t.production_year,
        c.name AS company_name,
        AVG(CASE WHEN ci.nr_order IS NOT NULL THEN ci.nr_order ELSE 0 END) AS avg_cast_order
    FROM 
        aka_title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        movie_info mi ON t.id = mi.movie_id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    WHERE 
        mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Awards')
        AND t.production_year BETWEEN 2000 AND 2023
        AND c.country_code IS NOT NULL
    GROUP BY 
        t.title, t.production_year, c.name
),
TopMovies AS (
    SELECT 
        title, 
        production_year, 
        company_name, 
        avg_cast_order,
        RANK() OVER (ORDER BY avg_cast_order DESC) AS rank_order
    FROM 
        RankedMovies
)
SELECT 
    title, 
    production_year, 
    company_name, 
    avg_cast_order
FROM 
    TopMovies
WHERE 
    rank_order <= 10;
