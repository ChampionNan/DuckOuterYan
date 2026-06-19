WITH RECURSIVE movie_hierarchy AS (
    SELECT m.id AS movie_id, m.title, m.production_year, 0 AS level
    FROM aka_title m
    WHERE m.kind_id = 1 
    
    UNION ALL
    
    SELECT m.id, m.title, m.production_year, mh.level + 1
    FROM aka_title m
    JOIN movie_hierarchy mh ON m.episode_of_id = mh.movie_id
),
cast_ranked AS (
    SELECT ci.movie_id, a.name AS actor_name, r.role, 
           ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN role_type r ON ci.role_id = r.id
),
movie_info_with_keywords AS (
    SELECT m.title, m.production_year, k.keyword, 
           COALESCE(mi.info, 'No information') AS info_text
    FROM aka_title m
    LEFT JOIN movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    LEFT JOIN movie_info mi ON m.id = mi.movie_id AND mi.info_type_id = 1 
),
company_overview AS (
    SELECT mc.movie_id, cn.name AS company_name,
           ct.kind AS company_type,
           COUNT(DISTINCT mc.company_id) AS total_companies
    FROM movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
    GROUP BY mc.movie_id, cn.name, ct.kind
),
final_output AS (
    SELECT mh.movie_id, mh.title, mh.production_year, 
           COALESCE(cr.actor_name, 'N/A') AS lead_actor,
           COALESCE(mw.keyword, 'No keywords') AS movie_keyword,
           co.company_name, co.company_type, co.total_companies
    FROM movie_hierarchy mh
    LEFT JOIN cast_ranked cr ON mh.movie_id = cr.movie_id AND cr.actor_rank = 1
    LEFT JOIN movie_info_with_keywords mw ON mh.title = mw.title AND mh.production_year = mw.production_year
    LEFT JOIN company_overview co ON mh.movie_id = co.movie_id
)
SELECT f.*, 
       CASE 
           WHEN f.total_companies IS NULL THEN 'No Companies' 
           ELSE f.company_type || ' (' || f.total_companies || ')'
       END AS company_details,
       LEFT(f.lead_actor, CASE WHEN LENGTH(f.lead_actor) > 10 THEN 10 ELSE LENGTH(f.lead_actor) END) AS short_actor_name
FROM final_output f
WHERE f.production_year BETWEEN 2000 AND 2023
  AND (f.movie_keyword <> 'No keywords' OR f.lead_actor <> 'N/A');
