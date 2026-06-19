
WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        ct.kind AS company_type,
        ak.name AS actor_name,
        ak.imdb_index AS actor_imdb_index,
        pi.info AS actor_info
    FROM 
        title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        aka_name ak ON cc.subject_id = ak.person_id
    LEFT JOIN 
        person_info pi ON ak.person_id = pi.person_id
    WHERE 
        t.production_year > 2000
        AND ct.kind LIKE 'Production%'
),
KeywordDetails AS (
    SELECT 
        t.title AS movie_title,
        k.keyword AS movie_keyword
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
)
SELECT 
    md.movie_title,
    md.production_year,
    md.company_type,
    md.actor_name,
    md.actor_imdb_index,
    md.actor_info,
    kd.movie_keyword
FROM 
    MovieDetails md
LEFT JOIN 
    KeywordDetails kd ON md.movie_title = kd.movie_title;
