WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC, t.title) AS year_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_description,
        COUNT(*) AS role_count
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
    GROUP BY
        c.movie_id, a.name, r.role
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
    rm.movie_id,
    rm.title,
    rm.production_year,
    ar.actor_name,
    ar.role_description,
    ar.role_count,
    ci.company_name,
    ci.company_type,
    CASE
        WHEN ar.role_count IS NULL THEN 'No Roles Found'
        ELSE CAST(ar.role_count AS text) || ' Roles'
    END AS role_summary,
    CASE
        WHEN rm.year_rank <= 3 THEN 'Top Recent Films'
        ELSE 'Other Films'
    END AS film_category
FROM
    RankedMovies rm
LEFT JOIN
    ActorRoles ar ON rm.movie_id = ar.movie_id
LEFT JOIN
    CompanyInfo ci ON rm.movie_id = ci.movie_id
WHERE
    (rm.production_year IS NOT NULL AND rm.production_year >= 2000)
    OR (ar.role_description IS NOT NULL AND ar.role_description LIKE '%Lead%');
