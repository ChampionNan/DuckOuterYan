WITH movie_cast AS (
    SELECT 
        t.title AS movie_title,
        a.name AS actor_name,
        a.imdb_index AS actor_index,
        c.nr_order AS role_order,
        rt.role AS role_name
    FROM 
        aka_title t
    JOIN 
        cast_info c ON t.id = c.movie_id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type rt ON c.role_id = rt.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2023
),
keyword_ranked AS (
    SELECT 
        m.id AS movie_id,
        k.keyword AS keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY k.id) AS keyword_rank
    FROM 
        aka_title m
    JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
movie_info_filtered AS (
    SELECT 
        mi.movie_id,
        mi.info AS additional_info,
        ROW_NUMBER() OVER (PARTITION BY mi.movie_id ORDER BY mi.id) AS info_rank
    FROM 
        movie_info mi
    WHERE 
        mi.info_type_id IN (SELECT id FROM info_type WHERE info LIKE '%Awards%')
)
SELECT 
    mc.movie_title,
    mc.actor_name,
    mc.actor_index,
    mc.role_order,
    mc.role_name,
    kr.keyword,
    mf.additional_info
FROM 
    movie_cast mc
LEFT JOIN 
    keyword_ranked kr ON mc.movie_title = (SELECT title FROM aka_title WHERE id = kr.movie_id)
LEFT JOIN 
    movie_info_filtered mf ON mc.movie_title = (SELECT title FROM aka_title WHERE id = mf.movie_id)
WHERE 
    kr.keyword_rank <= 3
    AND mf.info_rank = 1;
