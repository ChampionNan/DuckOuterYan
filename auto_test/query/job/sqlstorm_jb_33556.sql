WITH RECURSIVE MovieHierarchy AS (
    SELECT mt.id AS movie_id, 
           mt.title,
           mt.production_year,
           0 AS depth
    FROM aka_title mt
    WHERE mt.production_year >= 2000
    UNION ALL
    SELECT lt.linked_movie_id, 
           at.title,
           at.production_year,
           mh.depth + 1
    FROM movie_link lt
    JOIN aka_title at ON lt.linked_movie_id = at.id
    JOIN MovieHierarchy mh ON mh.movie_id = lt.movie_id
    WHERE mh.depth < 5
),
NullCompanyFilm AS (
    SELECT mc.movie_id, 
           c.name AS company_name, 
           ct.kind AS company_type,
           COALESCE(ct.kind, 'Unknown') AS company_type_coalesced
    FROM movie_companies mc
    LEFT JOIN company_name c ON mc.company_id = c.id
    LEFT JOIN company_type ct ON mc.company_type_id = ct.id
    WHERE c.name IS NULL
),
AverageRoleCount AS (
    SELECT ci.movie_id, 
           COUNT(DISTINCT ci.person_id) AS role_count
    FROM cast_info ci
    GROUP BY ci.movie_id
),
TopMovies AS (
    SELECT mh.movie_id,
           mh.title,
           mh.production_year,
           COALESCE(ac.role_count, 0) AS role_count
    FROM MovieHierarchy mh
    LEFT JOIN AverageRoleCount ac ON mh.movie_id = ac.movie_id
)
SELECT tm.title,
       tm.production_year,
       COALESCE(nc.company_name, 'Not Available') AS production_company,
       tm.role_count,
       CASE 
           WHEN tm.role_count < 5 THEN 'Low Role Count'
           WHEN tm.role_count BETWEEN 5 AND 15 THEN 'Average Role Count'
           ELSE 'High Role Count' 
       END AS role_intensity
FROM TopMovies tm
LEFT JOIN NullCompanyFilm nc ON tm.movie_id = nc.movie_id
WHERE tm.production_year BETWEEN 2010 AND 2022;
