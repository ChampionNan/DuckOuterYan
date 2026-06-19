
WITH MovieDetails AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        k.keyword AS keyword,
        co.name AS company_name,
        pt.info AS production_note
    FROM 
        aka_title AS m
    LEFT JOIN 
        movie_keyword AS mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword AS k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_companies AS mc ON m.id = mc.movie_id
    LEFT JOIN 
        company_name AS co ON mc.company_id = co.id
    LEFT JOIN 
        movie_info AS pt ON m.id = pt.movie_id AND pt.info_type_id = (SELECT id FROM info_type WHERE info = 'Production')
    WHERE 
        m.production_year BETWEEN 2000 AND 2023
    ORDER BY 
        m.production_year DESC
),
ActorDetails AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        cast_info AS c
    JOIN 
        aka_name AS a ON c.person_id = a.person_id
    JOIN 
        role_type AS r ON c.role_id = r.id
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    md.keyword,
    md.company_name,
    md.production_note,
    STRING_AGG(ad.actor_name || ' (' || ad.role_name || ')', ', ') AS actors
FROM 
    MovieDetails AS md
LEFT JOIN 
    ActorDetails AS ad ON md.movie_id = ad.movie_id
GROUP BY 
    md.movie_id, md.title, md.production_year, md.keyword, md.company_name, md.production_note;
