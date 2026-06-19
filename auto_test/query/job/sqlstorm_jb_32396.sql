
WITH RECURSIVE MovieHierarchy AS (
    SELECT m.id AS movie_id, 
           m.title AS movie_title, 
           1 AS level
    FROM aka_title m
    WHERE m.production_year = 2023

    UNION ALL

    SELECT m.id, 
           CONCAT(m.title, ' (Part of Series)') AS movie_title, 
           mh.level + 1
    FROM aka_title m
    JOIN movie_link ml ON m.id = ml.linked_movie_id
    JOIN MovieHierarchy mh ON ml.movie_id = mh.movie_id
),

ActorMovies AS (
    SELECT a.name AS actor_name,
           mt.title AS movie_title,
           mt.production_year,
           ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY mt.production_year DESC) AS rn
    FROM aka_name a
    JOIN cast_info ci ON a.person_id = ci.person_id
    JOIN aka_title mt ON ci.movie_id = mt.id
    WHERE a.name IS NOT NULL
),

LatestActorMovies AS (
    SELECT actor_name, 
           movie_title, 
           production_year
    FROM ActorMovies
    WHERE rn = 1
),

MoviesWithKeywords AS (
    SELECT mt.title, 
           STRING_AGG(kw.keyword, ', ') AS keywords
    FROM aka_title mt
    LEFT JOIN movie_keyword mk ON mt.id = mk.movie_id
    LEFT JOIN keyword kw ON mk.keyword_id = kw.id
    GROUP BY mt.title
),

FinalResults AS (
    SELECT mh.movie_id, 
           mh.movie_title, 
           la.actor_name, 
           la.production_year, 
           mk.keywords
    FROM MovieHierarchy mh
    LEFT JOIN LatestActorMovies la ON mh.movie_title LIKE '%' || la.movie_title || '%'
    LEFT JOIN MoviesWithKeywords mk ON mh.movie_title = mk.title
)

SELECT fr.movie_title,
       fr.actor_name,
       COALESCE(fr.production_year::TEXT, 'Unknown') AS production_year,
       COALESCE(fr.keywords, 'No Keywords') AS keywords,
       CASE 
           WHEN fr.keywords IS NULL OR fr.keywords = '' THEN 'No Keywords Available'
           ELSE fr.keywords 
       END AS final_keywords
FROM FinalResults fr;
