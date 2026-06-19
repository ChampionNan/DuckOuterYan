WITH MovieDetails AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        k.keyword AS movie_keyword,
        tc.kind AS title_kind
    FROM 
        title m
    LEFT JOIN 
        kind_type tc ON m.kind_id = tc.id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        m.production_year BETWEEN 2000 AND 2020
),

CastDetails AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        cp.kind AS cast_type
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
    JOIN 
        comp_cast_type cp ON ci.person_role_id = cp.id
    WHERE 
        r.role LIKE '%Actor%' 
),

CompanyDetails AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        ct.kind LIKE '%Production%'
)

SELECT 
    md.movie_title,
    md.production_year,
    md.movie_keyword,
    cd.actor_name,
    cd.role_name,
    cd.cast_type,
    co.company_name,
    co.company_type
FROM 
    MovieDetails md
JOIN 
    CastDetails cd ON md.movie_id = cd.movie_id
JOIN 
    CompanyDetails co ON md.movie_id = co.movie_id
WHERE 
    (md.movie_keyword IS NOT NULL OR cd.actor_name IS NOT NULL OR co.company_name IS NOT NULL);
