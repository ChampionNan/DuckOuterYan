WITH filtered_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword AS movie_keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
),
actor_details AS (
    SELECT 
        a.name,
        c.movie_id,
        COUNT(*) OVER (PARTITION BY a.person_id) AS movie_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    WHERE 
        a.name IS NOT NULL
),
company_details AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    ft.title,
    ft.production_year,
    ft.movie_keyword,
    ad.name AS actor_name,
    ad.movie_count,
    cd.company_name,
    cd.company_type
FROM 
    filtered_titles ft
LEFT JOIN 
    actor_details ad ON ft.title_id = ad.movie_id
LEFT JOIN 
    company_details cd ON ft.title_id = cd.movie_id
WHERE 
    (ft.movie_keyword IS NOT NULL OR ad.name IS NOT NULL)
    AND ft.year_rank <= 10;
