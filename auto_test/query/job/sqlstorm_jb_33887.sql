
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        ml.movie_id,
        ml.linked_movie_id,
        1 AS depth
    FROM 
        movie_link ml
    WHERE 
        ml.link_type_id = (SELECT id FROM link_type WHERE link = 'Sequel')
    
    UNION ALL
    
    SELECT 
        ml.movie_id,
        ml.linked_movie_id,
        mh.depth + 1
    FROM 
        movie_link ml
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.linked_movie_id
    WHERE 
        ml.link_type_id = (SELECT id FROM link_type WHERE link = 'Sequel')
),
cast_with_roles AS (
    SELECT 
        ci.movie_id,
        cn.name AS character_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_order
    FROM 
        cast_info ci
    JOIN 
        role_type rt ON ci.role_id = rt.id
    LEFT JOIN 
        char_name cn ON ci.person_id = cn.imdb_id
),
movie_details AS (
    SELECT 
        t.title,
        t.production_year,
        STRING_AGG(cwr.character_name || ' (' || cwr.role_name || ')', ', ') AS cast_info,
        mh.depth AS sequel_depth
    FROM 
        title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        movie_hierarchy mh ON t.id = mh.movie_id 
    LEFT JOIN 
        cast_with_roles cwr ON t.id = cwr.movie_id
    GROUP BY 
        t.title, t.production_year, mh.depth
)
SELECT 
    md.title,
    md.production_year,
    COALESCE(md.cast_info, 'No Cast') AS cast_info,
    CASE 
        WHEN md.sequel_depth IS NULL THEN 'No Sequels'
        ELSE CONCAT('Sequel Depth: ', md.sequel_depth)
    END AS sequel_info
FROM 
    movie_details md
WHERE 
    md.production_year >= 2000;
