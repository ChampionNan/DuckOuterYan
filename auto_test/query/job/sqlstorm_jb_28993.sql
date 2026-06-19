WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id, 
        m.title AS movie_title,
        m.production_year,
        k.keyword AS movie_keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY m.production_year DESC) AS rank
    FROM 
        aka_title m
    JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        m.production_year > 2000
), 
PersonRoles AS (
    SELECT 
        ci.movie_id,
        p.name AS person_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
), 
MovieInfo AS (
    SELECT 
        mi.movie_id, 
        mi.info AS additional_info,
        it.info AS info_type
    FROM 
        movie_info mi
    JOIN 
        info_type it ON mi.info_type_id = it.id
)
SELECT 
    rm.movie_title,
    rm.production_year,
    rm.movie_keyword,
    pr.person_name,
    pr.role_name,
    mi.additional_info
FROM 
    RankedMovies rm
LEFT JOIN 
    PersonRoles pr ON rm.movie_id = pr.movie_id AND pr.role_rank = 1
LEFT JOIN 
    MovieInfo mi ON rm.movie_id = mi.movie_id
WHERE 
    rm.rank = 1;
