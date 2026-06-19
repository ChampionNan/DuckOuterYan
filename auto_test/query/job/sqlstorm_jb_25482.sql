WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        k.keyword AS movie_keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS rank
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
ActorDetails AS (
    SELECT 
        c.movie_id, 
        a.name AS actor_name,
        r.role AS role_type,
        COUNT(c.id) OVER (PARTITION BY c.movie_id) AS actor_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieCompanyDetails AS (
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
    rt.title, 
    rt.production_year,
    rt.movie_keyword,
    ad.actor_name,
    ad.role_type,
    ad.actor_count,
    mcd.company_name,
    mcd.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    ActorDetails ad ON rt.title_id = ad.movie_id
LEFT JOIN 
    MovieCompanyDetails mcd ON rt.title_id = mcd.movie_id
WHERE 
    rt.rank <= 10;
