WITH movie_cast AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        c.id AS cast_info_id,
        ak.name AS actor_name,
        r.role AS role_name
    FROM 
        aka_title m
    JOIN 
        cast_info c ON m.id = c.movie_id
    JOIN 
        aka_name ak ON ak.person_id = c.person_id
    JOIN 
        role_type r ON r.id = c.role_id
    WHERE 
        m.production_year >= 2000
),
movie_keyword_info AS (
    SELECT 
        mk.movie_id,
        array_agg(k.keyword) AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
movie_info_details AS (
    SELECT 
        mi.movie_id,
        mi.info AS info_text,
        it.info AS info_type
    FROM 
        movie_info mi
    JOIN 
        info_type it ON it.id = mi.info_type_id
)
SELECT 
    mc.movie_id,
    mc.title,
    mc.production_year,
    mc.actor_name,
    mc.role_name,
    ki.keywords,
    pii.info_text,
    pii.info_type
FROM 
    movie_cast mc
LEFT JOIN 
    movie_keyword_info ki ON mc.movie_id = ki.movie_id
LEFT JOIN 
    movie_info_details pii ON mc.movie_id = pii.movie_id
WHERE 
    mc.role_name ILIKE '%lead%' AND 
    (pii.info_text IS NOT NULL OR ki.keywords IS NOT NULL);
