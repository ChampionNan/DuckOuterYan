WITH RankedTitles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT
        c.movie_id,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS role_rank
    FROM
        cast_info c
    JOIN
        role_type r ON c.role_id = r.id
    WHERE
        r.role IS NOT NULL
),
CompanyMovies AS (
    SELECT
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
    JOIN
        company_name c ON mc.company_id = c.id
    JOIN
        company_type ct ON mc.company_type_id = ct.id
)
SELECT
    rt.title,
    rt.production_year,
    ar.role,
    cm.company_name,
    cm.company_type
FROM
    RankedTitles rt
LEFT JOIN
    ActorRoles ar ON rt.title_id = ar.movie_id AND ar.role_rank = 1
LEFT JOIN
    CompanyMovies cm ON rt.title_id = cm.movie_id
WHERE
    rt.title_rank <= 10;
