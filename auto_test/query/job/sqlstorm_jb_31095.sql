WITH RECURSIVE movie_hierarchy AS (
    SELECT mt.movie_id, mt.title, mt.production_year, 
           1 AS level
    FROM aka_title mt
    WHERE mt.production_year IS NOT NULL
    
    UNION ALL
    
    SELECT mt.movie_id, mt.title, mt.production_year, 
           mh.level + 1
    FROM movie_link mlink
    JOIN movie_hierarchy mh ON mlink.movie_id = mh.movie_id
    JOIN aka_title mt ON mlink.linked_movie_id = mt.id
    WHERE mh.level < 5
),
ranked_cast AS (
    SELECT ci.movie_id, a.name AS actor_name, 
           ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
),
movie_keywords AS (
    SELECT mt.movie_id, 
           STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    JOIN aka_title mt ON mk.movie_id = mt.id
    GROUP BY mt.movie_id
)
SELECT mh.movie_id, mh.title, mh.production_year, 
       rc.actor_name, 
       COALESCE(mk.keywords, 'No Keywords') AS keywords, 
       mh.level
FROM movie_hierarchy mh
LEFT JOIN ranked_cast rc ON mh.movie_id = rc.movie_id AND rc.actor_rank <= 3
LEFT JOIN movie_keywords mk ON mh.movie_id = mk.movie_id
WHERE mh.production_year >= 2000;
