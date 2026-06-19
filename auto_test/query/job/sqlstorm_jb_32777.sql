
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        1 AS level
    FROM 
        aka_title mt
    WHERE 
        mt.production_year >= 2000  

    UNION ALL

    SELECT 
        ml.linked_movie_id,
        at.title,
        mh.level + 1
    FROM 
        movie_link ml
        JOIN aka_title at ON ml.linked_movie_id = at.id
        JOIN movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 5  
)

SELECT 
    a.name AS actor_name,
    mt.title AS movie_title,
    mt.production_year,
    COALESCE(ci.nr_order, 0) AS cast_order,
    ROW_NUMBER() OVER (PARTITION BY mt.id ORDER BY COALESCE(ci.nr_order, 999)) AS movie_rank,
    STRING_AGG(DISTINCT k.keyword, ', ') AS movie_keywords,
    CASE 
        WHEN mt.production_year < 2010 THEN 'Old'
        ELSE 'New'
    END AS age_category
FROM 
    aka_name a
    JOIN cast_info ci ON a.person_id = ci.person_id
    JOIN movie_hierarchy mh ON ci.movie_id = mh.movie_id
    LEFT JOIN movie_keyword mk ON mh.movie_id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    JOIN aka_title mt ON mh.movie_id = mt.id
WHERE 
    a.name IS NOT NULL 
    AND mt.title IS NOT NULL
GROUP BY 
    a.name, mt.id, mt.title, mt.production_year, ci.nr_order;
