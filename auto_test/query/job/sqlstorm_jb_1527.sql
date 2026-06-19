WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS row_num
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorCounts AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
FilteredMovies AS (
    SELECT 
        rm.title,
        rm.production_year,
        ac.actor_count
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorCounts ac ON rm.title_id = ac.movie_id
    WHERE 
        rm.row_num <= 10 AND (ac.actor_count IS NULL OR ac.actor_count > 5)
),
CompanyAndTitles AS (
    SELECT 
        c.name AS company_name,
        m.title,
        m.production_year
    FROM 
        movie_companies mc
    INNER JOIN 
        company_name c ON mc.company_id = c.id
    INNER JOIN 
        title m ON mc.movie_id = m.id
    WHERE 
        c.country_code = 'US'
)
SELECT 
    fm.title,
    fm.production_year,
    COALESCE(cat.company_name, 'Unknown') AS production_company,
    CASE 
        WHEN fm.actor_count IS NULL THEN 'No actors listed'
        ELSE CONCAT(fm.actor_count, ' actors')
    END AS actor_summary
FROM 
    FilteredMovies fm
LEFT JOIN 
    CompanyAndTitles cat ON fm.title = cat.title AND fm.production_year = cat.production_year;
