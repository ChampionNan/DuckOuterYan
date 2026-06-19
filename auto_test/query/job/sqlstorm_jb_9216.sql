
WITH MovieData AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        c.kind AS cast_type,
        t.id AS movie_id
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        comp_cast_type c ON ci.person_role_id = c.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2020
),
KeywordData AS (
    SELECT 
        mk.movie_id,
        k.keyword
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
CompanyData AS (
    SELECT 
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON mc.company_id = co.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    md.movie_title,
    md.production_year,
    md.actor_name,
    md.cast_type,
    kd.keyword,
    cd.company_name,
    cd.company_type
FROM 
    MovieData md
LEFT JOIN 
    KeywordData kd ON md.movie_id = kd.movie_id
LEFT JOIN 
    CompanyData cd ON md.movie_id = cd.movie_id;
