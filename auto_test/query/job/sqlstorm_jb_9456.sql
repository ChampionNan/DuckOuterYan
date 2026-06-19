
WITH filtered_titles AS (
    SELECT t.id, t.title, t.production_year, kt.kind 
    FROM title t 
    JOIN kind_type kt ON t.kind_id = kt.id 
    WHERE t.production_year BETWEEN 2000 AND 2020
), actor_details AS (
    SELECT ak.name AS actor_name, ak.person_id, ci.movie_id 
    FROM aka_name ak 
    JOIN cast_info ci ON ak.person_id = ci.person_id 
    WHERE ak.name IS NOT NULL
), movie_keywords AS (
    SELECT mk.movie_id, k.keyword 
    FROM movie_keyword mk 
    JOIN keyword k ON mk.keyword_id = k.id 
    WHERE k.keyword LIKE '%action%'
), company_details AS (
    SELECT mc.movie_id, cn.name AS company_name, ct.kind AS company_type 
    FROM movie_companies mc 
    JOIN company_name cn ON mc.company_id = cn.id 
    JOIN company_type ct ON mc.company_type_id = ct.id 
    WHERE cn.country_code = 'USA'
), complete_movie_info AS (
    SELECT ft.title, fa.actor_name, fk.keyword, fc.company_name, fc.company_type, ft.production_year
    FROM filtered_titles ft 
    LEFT JOIN actor_details fa ON ft.id = fa.movie_id 
    LEFT JOIN movie_keywords fk ON ft.id = fk.movie_id 
    LEFT JOIN company_details fc ON ft.id = fc.movie_id
)
SELECT title, actor_name, keyword, company_name, company_type 
FROM complete_movie_info 
WHERE actor_name IS NOT NULL;
