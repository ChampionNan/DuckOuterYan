WITH MovieTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword AS movie_keyword
    FROM
        title t
    JOIN
        movie_keyword mk ON t.id = mk.movie_id
    JOIN
        keyword k ON mk.keyword_id = k.id
    WHERE
        t.production_year >= 2000
),
ActorNames AS (
    SELECT 
        a.id AS actor_id,
        a.name,
        a.person_id,
        c.movie_id,
        r.role
    FROM
        aka_name a
    JOIN
        cast_info c ON a.person_id = c.person_id
    JOIN
        role_type r ON c.role_id = r.id
    WHERE
        a.name ILIKE '%Smith%'
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
    WHERE
        cn.country_code = 'USA'
),
MovieDetails AS (
    SELECT
        mt.title_id, 
        mt.title,
        mt.production_year,
        an.name AS actor_name,
        an.role AS actor_role,
        ci.company_name,
        ci.company_type
    FROM 
        MovieTitles mt
    LEFT JOIN
        ActorNames an ON mt.title_id = an.movie_id
    LEFT JOIN
        CompanyInfo ci ON mt.title_id = ci.movie_id
)
SELECT 
    md.title,
    md.production_year,
    md.actor_name,
    md.actor_role,
    md.company_name,
    md.company_type
FROM 
    MovieDetails md;
