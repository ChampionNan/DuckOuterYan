
WITH RecentMovies AS (
    SELECT DISTINCT m.id AS movie_id, m.title AS movie_title, m.production_year
    FROM aka_title m
    WHERE m.production_year >= 2020
), EncounteredPeople AS (
    SELECT DISTINCT c.person_id, a.name AS actor_name
    FROM cast_info c
    JOIN aka_name a ON c.person_id = a.person_id
    WHERE c.movie_id IN (SELECT movie_id FROM RecentMovies)
), ActorDetails AS (
    SELECT p.info_type_id, p.info AS actor_info, ep.actor_name
    FROM person_info p
    JOIN EncounteredPeople ep ON p.person_id = ep.person_id
), MovieCompanies AS (
    SELECT mc.movie_id, cn.name AS company_name, ct.kind AS company_type
    FROM movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
), MovieKeywords AS (
    SELECT mk.movie_id, k.keyword
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
), FinalReport AS (
    SELECT rm.movie_id, rm.movie_title, rm.production_year, 
           ep.actor_name, ad.actor_info, 
           mc.company_name, mc.company_type, 
           mk.keyword
    FROM RecentMovies rm
    LEFT JOIN EncounteredPeople ep ON rm.movie_id IN (SELECT c.movie_id FROM cast_info c WHERE c.person_id = ep.person_id)
    LEFT JOIN ActorDetails ad ON ep.actor_name = ad.actor_name
    LEFT JOIN MovieCompanies mc ON rm.movie_id = mc.movie_id
    LEFT JOIN MovieKeywords mk ON rm.movie_id = mk.movie_id
)
SELECT movie_id, movie_title, production_year, actor_name, actor_info, company_name, company_type, STRING_AGG(keyword, ', ') AS keywords
FROM FinalReport
GROUP BY movie_id, movie_title, production_year, actor_name, actor_info, company_name, company_type;
