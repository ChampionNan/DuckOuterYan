
WITH RECURSIVE MovieHierarchy AS (
    SELECT mt.id AS movie_id, mt.title, mt.production_year,
           1 AS level,
           NULL AS parent_id
    FROM aka_title mt
    WHERE mt.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT mt.id AS movie_id, mt.title, mt.production_year,
           mh.level + 1 AS level,
           mh.movie_id AS parent_id
    FROM aka_title mt
    JOIN MovieHierarchy mh ON mt.episode_of_id = mh.movie_id
),
CastDetails AS (
    SELECT ci.movie_id, p.name AS person_name, r.role AS role, 
           COUNT(*) OVER (PARTITION BY ci.movie_id) AS cast_count
    FROM cast_info ci
    JOIN aka_name p ON ci.person_id = p.person_id
    JOIN role_type r ON ci.role_id = r.id
),
CompanyDetails AS (
    SELECT mc.movie_id, c.name AS company_name, ct.kind AS company_type
    FROM movie_companies mc
    JOIN company_name c ON mc.company_id = c.id
    JOIN company_type ct ON mc.company_type_id = ct.id
),
MovieKeywords AS (
    SELECT mk.movie_id, STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
)

SELECT mh.movie_id, mh.title, mh.production_year,
       cd.person_name, cd.role, cd.cast_count,
       COALESCE(comp.company_name, 'Independent') AS production_company,
       COALESCE(comp.company_type, 'Unknown') AS company_type,
       mk.keywords
FROM MovieHierarchy mh
LEFT JOIN CastDetails cd ON mh.movie_id = cd.movie_id
LEFT JOIN CompanyDetails comp ON mh.movie_id = comp.movie_id
LEFT JOIN MovieKeywords mk ON mh.movie_id = mk.movie_id
WHERE mh.production_year BETWEEN 1990 AND 2023
  AND (cd.cast_count > 5 OR mk.keywords IS NOT NULL);
