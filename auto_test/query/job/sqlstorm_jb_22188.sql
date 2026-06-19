WITH RecursiveTitle AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        COALESCE(t.season_nr, 0) AS season,
        COALESCE(t.episode_nr, 0) AS episode,
        COALESCE(r.role, 'Unknown') AS role,
        COUNT(cc.movie_id) OVER (PARTITION BY t.id) AS cast_count,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY COALESCE(r.role, '9999'), t.production_year DESC) AS role_rank
    FROM 
        title t
        LEFT JOIN cast_info cc ON t.id = cc.movie_id
        LEFT JOIN role_type r ON cc.role_id = r.id
    WHERE
        t.production_year IS NOT NULL
        AND t.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE 'Movie%')
),
FilteredTitles AS (
    SELECT 
        title_id,
        title,
        production_year,
        season,
        episode,
        role,
        cast_count
    FROM 
        RecursiveTitle
    WHERE 
        cast_count > 3 AND
        role_rank = 1
),
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
        INNER JOIN company_name c ON mc.company_id = c.id
        LEFT JOIN company_type ct ON mc.company_type_id = ct.id
    WHERE 
        c.country_code IS NOT NULL
),
FinalResults AS (
    SELECT DISTINCT 
        ft.title_id,
        ft.title,
        ft.production_year,
        ft.season,
        ft.episode,
        ft.role,
        cm.company_name,
        cm.company_type,
        ROUND(EXTRACT(EPOCH FROM cast('2024-10-01 12:34:56' as timestamp) - timestamp '1970-01-01') / 60, 2) AS elapsed_minutes
    FROM 
        FilteredTitles ft
        LEFT JOIN CompanyMovies cm ON ft.title_id = cm.movie_id
)
SELECT 
    title_id, 
    title, 
    production_year,
    season,
    episode,
    role,
    COALESCE(company_name, 'Independent') AS company_name,
    COALESCE(company_type, 'N/A') AS company_type,
    elapsed_minutes
FROM 
    FinalResults
WHERE 
    (role IS NOT NULL OR company_name IS NOT NULL) AND 
    (production_year BETWEEN 2000 AND 2020 OR season > 0);
