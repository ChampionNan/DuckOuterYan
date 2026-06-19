WITH movie_cast AS (
    SELECT 
        t.title AS movie_title,
        a.name AS actor_name,
        c.nr_order AS role_order,
        rt.role AS role_type
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.person_id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type rt ON c.role_id = rt.id
    WHERE 
        t.production_year >= 2000
),
movie_keywords AS (
    SELECT 
        t.title AS movie_title,
        ARRAY_AGG(k.keyword) AS keywords
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.title
),
movie_info_extract AS (
    SELECT 
        t.title AS movie_title,
        mi.info AS movie_info
    FROM 
        aka_title t
    JOIN 
        movie_info mi ON t.id = mi.movie_id
    WHERE 
        mi.note LIKE '%info%'
)
SELECT 
    mc.movie_title,
    mc.actor_name,
    mc.role_order,
    mc.role_type,
    COALESCE(mk.keywords, '{}') AS keywords,
    COALESCE(me.movie_info, 'No additional info') AS movie_info
FROM 
    movie_cast mc
LEFT JOIN 
    movie_keywords mk ON mc.movie_title = mk.movie_title
LEFT JOIN 
    movie_info_extract me ON mc.movie_title = me.movie_title;
