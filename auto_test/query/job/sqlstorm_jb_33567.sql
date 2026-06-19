WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id, 
        mt.title, 
        mt.production_year, 
        mt.kind_id,
        1 AS level
    FROM 
        aka_title mt
    WHERE 
        mt.production_year >= 2000

    UNION ALL

    SELECT 
        ml.linked_movie_id AS movie_id, 
        at.title, 
        at.production_year, 
        at.kind_id,
        mh.level + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title at ON ml.linked_movie_id = at.id
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 3
)

SELECT 
    a.name AS actor_name,
    mt.title AS movie_title,
    mt.production_year,
    COALESCE(ki.keyword, 'N/A') AS keyword,
    ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY mt.production_year DESC) AS actor_movie_rank,
    CONCAT(a.name, ' starred in ', mt.title) AS actor_movie_info
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    movie_hierarchy mt ON ci.movie_id = mt.movie_id
LEFT JOIN 
    movie_keyword mk ON mt.movie_id = mk.movie_id
LEFT JOIN 
    keyword ki ON mk.keyword_id = ki.id
WHERE 
    a.name IS NOT NULL 
    AND mt.production_year IS NOT NULL 
    AND (mt.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE '%movie%')
         OR mt.production_year > 2005);
