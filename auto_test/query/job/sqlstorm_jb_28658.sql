WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        r.role AS actor_role,
        c.note AS cast_note
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
    WHERE 
        t.production_year BETWEEN 1990 AND 2023
        AND a.name IS NOT NULL
),
KeywordDetails AS (
    SELECT
        t.title AS movie_title,
        k.keyword AS movie_keyword
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.phonetic_code IS NOT NULL
),
CompanyDetails AS (
    SELECT 
        t.title AS movie_title,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        aka_title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    md.movie_title,
    md.production_year,
    md.actor_name,
    md.actor_role,
    md.cast_note,
    kd.movie_keyword,
    cd.company_name,
    cd.company_type
FROM 
    MovieDetails md
LEFT JOIN 
    KeywordDetails kd ON md.movie_title = kd.movie_title
LEFT JOIN 
    CompanyDetails cd ON md.movie_title = cd.movie_title;
