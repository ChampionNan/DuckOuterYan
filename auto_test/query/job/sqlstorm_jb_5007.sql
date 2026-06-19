WITH MovieDetails AS (
    SELECT a.name AS actor_name, t.title AS movie_title, t.production_year, k.keyword AS movie_keyword
    FROM aka_name a
    JOIN cast_info ci ON a.person_id = ci.person_id
    JOIN aka_title t ON ci.movie_id = t.id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
), CompanyDetails AS (
    SELECT c.name AS company_name, ct.kind AS company_type, mc.movie_id
    FROM company_name c
    JOIN movie_companies mc ON c.id = mc.company_id
    JOIN company_type ct ON mc.company_type_id = ct.id
), CompleteCast AS (
    SELECT cc.movie_id, COUNT(DISTINCT cc.subject_id) AS total_cast
    FROM complete_cast cc
    GROUP BY cc.movie_id
)
SELECT md.actor_name, md.movie_title, md.production_year, md.movie_keyword, cd.company_name, cd.company_type, cc.total_cast
FROM MovieDetails md
JOIN CompanyDetails cd ON md.production_year = cd.movie_id
JOIN CompleteCast cc ON md.production_year = cc.movie_id
WHERE md.movie_keyword IS NOT NULL;
