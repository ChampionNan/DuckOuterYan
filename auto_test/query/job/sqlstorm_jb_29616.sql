
WITH RankedTitles AS (
    SELECT 
        at.id AS title_id,
        at.title,
        at.production_year,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM 
        aka_title at
    LEFT JOIN 
        movie_companies mc ON at.movie_id = mc.movie_id
    LEFT JOIN 
        cast_info ci ON at.movie_id = ci.movie_id
    GROUP BY 
        at.id, at.title, at.production_year
), 
FilteredTitles AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        rt.cast_count,
        ROW_NUMBER() OVER (PARTITION BY rt.production_year ORDER BY rt.cast_count DESC) AS rank
    FROM 
        RankedTitles rt
    WHERE 
        rt.production_year IS NOT NULL
)
SELECT 
    ft.title AS Title,
    ft.production_year AS ProductionYear,
    ft.cast_count AS CastCount,
    pi.info AS PersonInfo,
    cn.name AS CompanyName
FROM 
    FilteredTitles ft
LEFT JOIN 
    complete_cast cc ON ft.title_id = cc.movie_id
LEFT JOIN 
    person_info pi ON cc.subject_id = pi.person_id
LEFT JOIN 
    movie_companies mc ON ft.title_id = mc.movie_id
LEFT JOIN 
    company_name cn ON mc.company_id = cn.id
WHERE 
    ft.rank <= 5;
