WITH MovieWithKeywords AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        k.keyword
    FROM 
        title m
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
),
MovieCast AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        title m
    JOIN 
        complete_cast cc ON m.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.person_id
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
CompanyInfo AS (
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
)
SELECT 
    mwk.movie_id,
    mwk.title AS movie_title,
    mwk.keyword AS movie_keyword,
    mc.actor_name AS lead_actor,
    mc.role_name AS actor_role,
    ci.company_name,
    ci.company_type
FROM 
    MovieWithKeywords mwk
JOIN 
    MovieCast mc ON mwk.movie_id = mc.movie_id
JOIN 
    CompanyInfo ci ON mwk.movie_id = ci.movie_id
WHERE 
    mwk.keyword LIKE '%action%' 
    AND mc.role_name = 'lead';
