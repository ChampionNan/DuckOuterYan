WITH RECURSIVE movie_hierarchy AS (
    SELECT mt1.movie_id, mt1.title, mt1.production_year, 1 AS depth
    FROM aka_title mt1
    WHERE mt1.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
    
    UNION ALL
    
    SELECT mt2.movie_id, mt2.title, mt2.production_year, mh.depth + 1
    FROM movie_link ml
    JOIN movie_hierarchy mh ON ml.movie_id = mh.movie_id
    JOIN aka_title mt2 ON ml.linked_movie_id = mt2.movie_id
    WHERE mt2.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
)
SELECT 
    ak.name AS actor_name,
    mt.title AS movie_title,
    mt.production_year,
    COALESCE(inf.info, 'No information available') AS additional_info,
    COUNT(ca.id) AS character_count,
    ROW_NUMBER() OVER (PARTITION BY ak.id ORDER BY mt.production_year DESC) AS actor_movie_rank
FROM aka_name ak
JOIN cast_info ca ON ak.person_id = ca.person_id
JOIN aka_title mt ON ca.movie_id = mt.movie_id
LEFT JOIN movie_info inf ON mt.id = inf.movie_id AND inf.info_type_id = (SELECT id FROM info_type WHERE info = 'Summary')
LEFT JOIN movie_keyword mk ON mt.id = mk.movie_id
LEFT JOIN keyword k ON mk.keyword_id = k.id
JOIN movie_hierarchy mh ON mt.id = mh.movie_id
WHERE ak.name IS NOT NULL
    AND mt.production_year BETWEEN 1990 AND 2020
    AND (k.keyword LIKE 'Action%' OR k.keyword IS NULL)
GROUP BY ak.id, ak.name, mt.title, mt.production_year, inf.info;
