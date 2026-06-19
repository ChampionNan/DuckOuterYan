
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_by_title
    FROM 
        title t
    WHERE 
        t.production_year > 2000
),
CastDetails AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        c.nr_order
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
KeywordDetails AS (
    SELECT 
        mk.movie_id,
        k.keyword
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        comp.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name comp ON mc.company_id = comp.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
MovieInfo AS (
    SELECT 
        m.movie_id,
        STRING_AGG(m.info, ', ') AS movie_info
    FROM 
        movie_info m
    GROUP BY 
        m.movie_id
)

SELECT 
    rm.movie_id,
    rm.movie_title,
    rm.production_year,
    cd.actor_name,
    cd.role_name,
    cd.nr_order,
    kd.keyword,
    comp.company_name,
    comp.company_type,
    mi.movie_info
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    KeywordDetails kd ON rm.movie_id = kd.movie_id
LEFT JOIN 
    CompanyDetails comp ON rm.movie_id = comp.movie_id
LEFT JOIN 
    MovieInfo mi ON rm.movie_id = mi.movie_id
WHERE 
    rm.rank_by_title <= 5;
