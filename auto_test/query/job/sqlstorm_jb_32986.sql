WITH RECURSIVE movie_hierarchy AS (
    SELECT mt.id AS movie_id, mt.title, mt.production_year, 1 AS level
    FROM aka_title mt
    WHERE mt.kind_id = 1  

    UNION ALL

    SELECT m.id, m.title, m.production_year, mh.level + 1
    FROM movie_link ml
    JOIN movie_hierarchy mh ON ml.movie_id = mh.movie_id
    JOIN aka_title m ON ml.linked_movie_id = m.id
    WHERE mh.level < 3  
),
cast_details AS (
    SELECT c.movie_id, a.name AS actor_name, 
           row_number() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM cast_info c
    JOIN aka_name a ON c.person_id = a.person_id
    WHERE a.name IS NOT NULL
),
keyword_count AS (
    SELECT mk.movie_id, COUNT(mk.keyword_id) AS keyword_count
    FROM movie_keyword mk
    GROUP BY mk.movie_id
)
SELECT 
    mh.movie_id,
    mh.title,
    mh.production_year,
    COALESCE(cd.actor_name, 'No Actors') AS lead_actor,
    cd.actor_rank,
    COALESCE(kc.keyword_count, 0) AS total_keywords,
    CASE 
        WHEN mh.production_year < 2000 THEN 'Classic'
        WHEN mh.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS era
FROM movie_hierarchy mh
LEFT JOIN cast_details cd ON mh.movie_id = cd.movie_id AND cd.actor_rank = 1  
LEFT JOIN keyword_count kc ON mh.movie_id = kc.movie_id
WHERE mh.production_year IS NOT NULL;
