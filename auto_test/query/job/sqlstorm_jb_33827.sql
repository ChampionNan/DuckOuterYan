WITH RECURSIVE movie_succession AS (
    SELECT mt.movie_id, mt.linked_movie_id, 1 AS depth
    FROM movie_link mt
    WHERE mt.link_type_id = (SELECT id FROM link_type WHERE link = 'sequel')

    UNION ALL

    SELECT ml.movie_id, ml.linked_movie_id, ms.depth + 1
    FROM movie_link ml
    JOIN movie_succession ms ON ml.movie_id = ms.linked_movie_id
    WHERE ml.link_type_id = (SELECT id FROM link_type WHERE link = 'sequel')
),

cast_with_role AS (
    SELECT ci.movie_id, a.name AS actor_name, r.role AS role_type,
           ROW_NUMBER() OVER(PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS rnum
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN role_type r ON ci.role_id = r.id
),

movie_keywords AS (
    SELECT mt.movie_id, STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mt
    JOIN keyword k ON mt.keyword_id = k.id
    GROUP BY mt.movie_id
),

filtered_cast AS (
    SELECT c.movie_id, c.actor_name, c.role_type
    FROM cast_with_role c
    WHERE c.role_type LIKE '%Director%'
),

summary AS (
    SELECT 
        t.title,
        t.production_year,
        m.depth AS sequel_depth,
        f.actor_name,
        f.role_type,
        COALESCE(mk.keywords, 'No keywords') AS keywords
    FROM title t
    LEFT JOIN movie_succession m ON t.id = m.movie_id
    LEFT JOIN filtered_cast f ON t.id = f.movie_id
    LEFT JOIN movie_keywords mk ON t.id = mk.movie_id
    WHERE t.production_year >= 2000
    ORDER BY t.production_year DESC, sequel_depth ASC
)

SELECT 
    s.title,
    s.production_year,
    s.sequel_depth,
    s.actor_name,
    s.role_type,
    s.keywords
FROM summary s
WHERE (s.sequel_depth IS NULL OR s.sequel_depth < 3) 
AND (s.actor_name IS NOT NULL OR s.role_type IS NOT NULL);
