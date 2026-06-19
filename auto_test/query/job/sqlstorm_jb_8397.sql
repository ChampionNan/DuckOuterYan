
WITH MovieDetails AS (
    SELECT t.id AS movie_id, t.title, t.production_year, c.name AS company_name, STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM aka_title t
    JOIN movie_companies mc ON t.id = mc.movie_id
    JOIN company_name c ON mc.company_id = c.id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY t.id, t.title, t.production_year, c.name
),
ActorDetails AS (
    SELECT a.name AS actor_name, t.title, t.production_year
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN aka_title t ON ci.movie_id = t.id
    WHERE ci.nr_order < 10
),
FullDetails AS (
    SELECT md.movie_id, md.title, md.production_year, md.company_name, ad.actor_name, md.keywords
    FROM MovieDetails md
    JOIN ActorDetails ad ON md.title = ad.title AND md.production_year = ad.production_year
)
SELECT *
FROM FullDetails
WHERE company_name LIKE 'A%';
