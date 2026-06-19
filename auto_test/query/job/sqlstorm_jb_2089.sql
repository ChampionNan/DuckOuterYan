WITH RankedTitles AS (
    SELECT 
        a.title,
        a.production_year,
        k.keyword,
        RANK() OVER (PARTITION BY k.keyword ORDER BY a.production_year DESC) AS rank_year,
        COALESCE(cn.name, 'Unknown') AS company_name
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_companies mc ON a.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        a.production_year IS NOT NULL
        AND a.note IS DISTINCT FROM 'N/A'
),
FilteredTitles AS (
    SELECT 
        title,
        production_year,
        keyword,
        company_name
    FROM 
        RankedTitles
    WHERE 
        rank_year <= 3
)
SELECT 
    ft.title,
    ft.production_year,
    ft.keyword,
    ft.company_name,
    COALESCE(ci.note, 'No Role') AS role_note
FROM 
    FilteredTitles ft
LEFT JOIN 
    cast_info ci ON ci.movie_id = (SELECT id FROM aka_title WHERE title = ft.title LIMIT 1)
WHERE 
    ft.keyword IN (SELECT keyword FROM keyword WHERE keyword LIKE '%Drama%');
