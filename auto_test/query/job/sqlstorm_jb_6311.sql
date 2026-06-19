WITH RecentMovies AS (
    SELECT mt.id AS movie_id, mt.title, mt.production_year
    FROM aka_title mt
    WHERE mt.production_year >= 2020
), MovieCast AS (
    SELECT ci.movie_id, COUNT(DISTINCT ci.person_id) AS cast_count
    FROM cast_info ci
    INNER JOIN RecentMovies rm ON ci.movie_id = rm.movie_id
    GROUP BY ci.movie_id
), CastDetails AS (
    SELECT rm.movie_id, rm.title, rm.production_year, mc.cast_count
    FROM RecentMovies rm
    LEFT JOIN MovieCast mc ON rm.movie_id = mc.movie_id
), CompanyMovies AS (
    SELECT mc.movie_id, cn.name AS company_name, ct.kind AS company_type
    FROM movie_companies mc
    INNER JOIN company_name cn ON mc.company_id = cn.id
    INNER JOIN company_type ct ON mc.company_type_id = ct.id
    WHERE cn.country_code = 'USA'
), CompleteDetails AS (
    SELECT cd.title, cd.production_year, cd.cast_count, cm.company_name, cm.company_type
    FROM CastDetails cd
    LEFT JOIN CompanyMovies cm ON cd.movie_id = cm.movie_id
)
SELECT *
FROM CompleteDetails
WHERE cast_count IS NOT NULL;
