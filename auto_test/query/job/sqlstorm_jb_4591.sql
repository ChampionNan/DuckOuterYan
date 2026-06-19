WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
PersonRoleCounts AS (
    SELECT 
        ci.person_id,
        COUNT(ci.role_id) AS role_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.person_id
),
FilteredPersons AS (
    SELECT 
        a.id AS person_id,
        a.name,
        prc.role_count
    FROM 
        aka_name a
    JOIN 
        PersonRoleCounts prc ON a.person_id = prc.person_id
    WHERE 
        prc.role_count > 5
)
SELECT 
    fp.name AS actor_name,
    rt.title AS movie_title,
    rt.production_year,
    COALESCE(mi.info, 'No info') AS movie_info
FROM 
    FilteredPersons fp
LEFT JOIN 
    cast_info ci ON fp.person_id = ci.person_id
JOIN 
    RankedTitles rt ON ci.movie_id = rt.title_id
LEFT JOIN 
    movie_info mi ON rt.title_id = mi.movie_id AND mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'summary')
WHERE 
    rt.title_rank <= 10;
