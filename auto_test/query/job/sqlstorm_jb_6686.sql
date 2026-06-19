WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS year_rank
    FROM 
        title t
),
FilteredTitles AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year
    FROM 
        RankedTitles rt
    WHERE 
        rt.year_rank <= 10
),
MovieCompaniesInfo AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
MovieDetails AS (
    SELECT 
        ft.title,
        ft.production_year,
        mci.company_name,
        mci.company_type,
        COUNT(ki.id) AS keyword_count
    FROM 
        FilteredTitles ft
    LEFT JOIN 
        complete_cast cc ON ft.title_id = cc.movie_id
    LEFT JOIN 
        MovieCompaniesInfo mci ON ft.title_id = mci.movie_id
    LEFT JOIN 
        movie_keyword mk ON ft.title_id = mk.movie_id
    LEFT JOIN 
        keyword ki ON mk.keyword_id = ki.id
    GROUP BY 
        ft.title, ft.production_year, mci.company_name, mci.company_type
)
SELECT 
    title,
    production_year,
    company_name,
    company_type,
    keyword_count
FROM 
    MovieDetails;
