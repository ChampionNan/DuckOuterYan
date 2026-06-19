WITH movie_actor_info AS (
    SELECT 
        a.name AS actor_name,
        t.title AS movie_title,
        c.nr_order AS cast_order,
        t.production_year,
        rt.role AS role
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        aka_title t ON c.movie_id = t.movie_id
    JOIN 
        role_type rt ON c.role_id = rt.id
    WHERE 
        t.production_year >= 2000
        AND rt.role IN ('Actor', 'Actress')
),
keyword_movies AS (
    SELECT 
        m.movie_id,
        k.keyword
    FROM 
        movie_keyword m 
    JOIN 
        keyword k ON m.keyword_id = k.id
),
company_movies AS (
    SELECT 
        mc.movie_id,
        com.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name com ON mc.company_id = com.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
movie_info_extended AS (
    SELECT 
        mi.movie_id,
        mi.info
    FROM 
        movie_info mi 
    WHERE 
        mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'Synopsis')
)

SELECT 
    mai.actor_name,
    mai.movie_title,
    mai.production_year,
    mai.role,
    km.keyword,
    cm.company_name,
    cm.company_type,
    mie.info AS movie_synopsis
FROM 
    movie_actor_info mai
LEFT JOIN 
    keyword_movies km ON mai.movie_title = (SELECT title FROM aka_title WHERE movie_id = km.movie_id LIMIT 1)
LEFT JOIN 
    company_movies cm ON mai.movie_title = (SELECT title FROM aka_title WHERE movie_id = cm.movie_id LIMIT 1)
LEFT JOIN 
    movie_info_extended mie ON mai.movie_title = (SELECT title FROM aka_title WHERE movie_id = mie.movie_id LIMIT 1);
