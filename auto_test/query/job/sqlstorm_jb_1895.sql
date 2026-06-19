WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
CastCounts AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS cast_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
FilteredCompanies AS (
    SELECT 
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON mc.company_id = co.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        co.country_code = 'USA'
)
SELECT 
    rt.title,
    rt.production_year,
    cc.cast_count,
    fc.company_name,
    fc.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    CastCounts cc ON rt.title_id = cc.movie_id
LEFT JOIN 
    FilteredCompanies fc ON rt.title_id = fc.movie_id
WHERE 
    rt.title_rank <= 10
    AND (cc.cast_count IS NULL OR cc.cast_count > 5);
