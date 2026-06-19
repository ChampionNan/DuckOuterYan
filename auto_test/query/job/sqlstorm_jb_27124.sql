
WITH actor_movie_info AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords,
        p.info AS actor_info
    FROM aka_name a
    JOIN cast_info ci ON a.person_id = ci.person_id
    JOIN aka_title t ON ci.movie_id = t.movie_id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    LEFT JOIN person_info p ON a.person_id = p.person_id
    WHERE t.production_year BETWEEN 2000 AND 2020
    AND a.name LIKE '%Smith%'
    GROUP BY a.id, a.name, t.title, t.production_year, p.info
),
company_movie_details AS (
    SELECT 
        co.name AS company_name,
        t.title AS movie_title,
        t.production_year,
        ct.kind AS company_type
    FROM movie_companies mc
    JOIN company_name co ON mc.company_id = co.id
    JOIN aka_title t ON mc.movie_id = t.movie_id
    JOIN company_type ct ON mc.company_type_id = ct.id
    WHERE ct.kind = 'Production'
    AND t.production_year > 2010
),
final_benchmark AS (
    SELECT 
        ami.actor_id,
        ami.actor_name,
        ami.movie_title,
        ami.production_year,
        ami.keywords,
        ami.actor_info,
        cmd.company_name,
        cmd.company_type
    FROM actor_movie_info ami
    JOIN company_movie_details cmd ON ami.movie_title = cmd.movie_title AND ami.production_year = cmd.production_year
)
SELECT 
    actor_name,
    movie_title,
    production_year,
    keywords,
    actor_info,
    company_name,
    company_type
FROM final_benchmark;
