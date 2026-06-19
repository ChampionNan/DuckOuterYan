
WITH ActorMovies AS (
    SELECT a.id AS actor_id, 
           a.name AS actor_name, 
           m.production_year, 
           m.title AS movie_title
    FROM aka_name a
    JOIN cast_info ci ON a.person_id = ci.person_id
    JOIN aka_title m ON ci.movie_id = m.id
),
MovieDetails AS (
    SELECT m.id AS movie_id, 
           m.title, 
           STRING_AGG(DISTINCT k.keyword, ', ') AS keywords, 
           c.name AS company_name
    FROM aka_title m
    JOIN movie_companies mc ON m.id = mc.movie_id
    JOIN company_name c ON mc.company_id = c.id
    LEFT JOIN movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY m.id, c.name
),
ActorInfo AS (
    SELECT p.id AS person_id, 
           p.name AS person_name, 
           COALESCE(ai.info, 'No Info') AS additional_info
    FROM name p
    LEFT JOIN person_info ai ON p.imdb_id = ai.person_id
)
SELECT a.actor_name, 
       a.movie_title, 
       a.production_year, 
       d.keywords, 
       d.company_name, 
       i.additional_info
FROM ActorMovies a
JOIN MovieDetails d ON a.movie_title = d.title
JOIN ActorInfo i ON a.actor_id = i.person_id
WHERE a.production_year >= 2000;
