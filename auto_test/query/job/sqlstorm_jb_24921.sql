WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS title_rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        aka_title t ON c.movie_id = t.movie_id
),
FilteredTitles AS (
    SELECT 
        rt.aka_id,
        rt.title,
        rt.production_year
    FROM 
        RankedTitles rt
    WHERE 
        rt.title_rank <= 5
),
MovieCompanyInfo AS (
    SELECT 
        mc.movie_id,
        mc.company_id,
        cn.name AS company_name,
        COUNT(*) OVER (PARTITION BY mc.company_id) AS company_movie_count
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        cn.country_code IS NOT NULL
),
TitleInfo AS (
    SELECT
        t.title,
        MIN(m.info) AS earliest_info
    FROM 
        title t
    LEFT JOIN 
        movie_info m ON t.id = m.movie_id
    WHERE 
        m.info IS NOT NULL
    GROUP BY 
        t.title
)
SELECT 
    ft.aka_id,
    ft.title,
    ft.production_year,
    ci.company_name,
    ci.company_movie_count,
    ti.earliest_info
FROM 
    FilteredTitles ft
LEFT JOIN 
    MovieCompanyInfo ci ON ft.production_year = ci.movie_id
LEFT JOIN 
    TitleInfo ti ON ft.title = ti.title
WHERE 
    ci.company_movie_count > 1 
    AND (ti.earliest_info IS NOT NULL OR ft.production_year > 2000);
