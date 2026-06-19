WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS ranking,
        COUNT(c.person_id) AS cast_count
    FROM 
        title t
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.person_id
    GROUP BY 
        t.id, t.title, t.production_year
),

TopTitles AS (
    SELECT 
        rt.title_id, 
        rt.title, 
        rt.production_year, 
        rt.cast_count
    FROM 
        RankedTitles rt 
    WHERE 
        rt.ranking = 1
),

PersonInfo AS (
    SELECT 
        a.id AS person_id, 
        a.name, 
        p.info AS person_info
    FROM 
        aka_name a
    LEFT JOIN 
        person_info p ON a.person_id = p.person_id
    WHERE 
        p.info_type_id = (SELECT id FROM info_type WHERE info = 'birthplace') 
        OR p.info_type_id IS NULL
)

SELECT 
    tt.title, 
    tt.production_year, 
    pi.name AS actor_name, 
    pi.person_info
FROM 
    TopTitles tt
LEFT JOIN 
    cast_info ci ON tt.title_id = ci.movie_id
LEFT JOIN 
    PersonInfo pi ON ci.person_id = pi.person_id
WHERE 
    tt.cast_count > 0;
