WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) as title_rank
    FROM title t
    WHERE t.production_year BETWEEN 2000 AND 2020
),
movie_details AS (
    SELECT
        m.id AS movie_id,
        m.info AS movie_info,
        k.keyword AS movie_keyword
    FROM movie_info m
    JOIN movie_keyword mk ON m.movie_id = mk.movie_id
    JOIN keyword k ON mk.keyword_id = k.id
    WHERE m.info_type_id = (SELECT id FROM info_type WHERE info = 'Plot')
),
cast_details AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY a.name) as actor_rank
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN role_type rt ON ci.role_id = rt.id
),
movie_company_details AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
),
final_output AS (
    SELECT 
        rt.title,
        rt.production_year,
        cd.actor_name,
        cd.role_name,
        m.movie_info,
        mc.company_name,
        mc.company_type,
        rt.title_rank,
        cd.actor_rank
    FROM ranked_titles rt
    LEFT JOIN cast_details cd ON rt.title_id = cd.movie_id
    LEFT JOIN movie_details m ON rt.title_id = m.movie_id
    LEFT JOIN movie_company_details mc ON rt.title_id = mc.movie_id
)
SELECT 
    title,
    production_year,
    actor_name,
    role_name,
    movie_info,
    company_name,
    company_type,
    title_rank,
    actor_rank
FROM final_output
WHERE title_rank <= 10 AND actor_rank <= 5;
