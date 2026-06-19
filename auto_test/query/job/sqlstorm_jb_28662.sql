WITH movie_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        k.keyword
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2020
),
actor_aka_names AS (
    SELECT 
        a.id AS name_id,
        a.person_id,
        a.name,
        p.gender
    FROM 
        aka_name a
    JOIN 
        name p ON a.person_id = p.id
    WHERE 
        a.name IS NOT NULL
),
cast_details AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        m.title AS movie_title,
        m.production_year
    FROM 
        cast_info c
    JOIN 
        actor_aka_names a ON c.person_id = a.person_id
    JOIN 
        movie_titles m ON c.movie_id = m.title_id
)
SELECT 
    cd.movie_title,
    cd.production_year,
    STRING_AGG(DISTINCT cd.actor_name, ', ') AS actors_list
FROM 
    cast_details cd
GROUP BY 
    cd.movie_title, cd.production_year;
