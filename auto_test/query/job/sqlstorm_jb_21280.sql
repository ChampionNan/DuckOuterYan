WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY RANDOM()) AS rank
    FROM
        aka_title t
    WHERE
        t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie')
        AND t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        COUNT(*) OVER (PARTITION BY c.movie_id, r.role) AS role_count
    FROM
        cast_info c
    INNER JOIN
        aka_name a ON c.person_id = a.person_id
    INNER JOIN
        role_type r ON c.role_id = r.id
),
MovieDetails AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(ar.actor_name, 'No Cast') AS actor_name,
        ar.role_name,
        ar.role_count
    FROM
        RankedMovies rm
    LEFT JOIN
        ActorRoles ar ON rm.movie_id = ar.movie_id
    WHERE 
        rm.rank <= 5
),
CompanyInfo AS (
    SELECT
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        COUNT(*) AS company_count
    FROM
        movie_companies mc
    JOIN
        company_name c ON mc.company_id = c.id
    JOIN
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY
        mc.movie_id, c.name, ct.kind
),
ResultSet AS (
    SELECT
        md.title,
        md.production_year,
        md.actor_name,
        md.role_name,
        COALESCE(ci.company_name, 'Independent') AS company_name,
        ci.company_type,
        md.role_count,
        RANK() OVER (PARTITION BY md.production_year ORDER BY md.role_count DESC) AS movie_rank
    FROM
        MovieDetails md
    FULL OUTER JOIN
        CompanyInfo ci ON md.movie_id = ci.movie_id
)
SELECT
    title,
    production_year,
    actor_name,
    role_name,
    company_name,
    company_type,
    role_count,
    movie_rank
FROM
    ResultSet
WHERE
    (movie_rank = 1 OR role_count > 2 OR company_type IS NOT NULL);
