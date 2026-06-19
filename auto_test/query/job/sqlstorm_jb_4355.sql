
WITH RankedTitles AS (
    SELECT
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
ActorRoleCounts AS (
    SELECT
        ai.name,
        COUNT(ci.role_id) AS role_count
    FROM
        aka_name ai
    JOIN
        cast_info ci ON ai.person_id = ci.person_id
    GROUP BY
        ai.name
),
CompanyDetails AS (
    SELECT
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
    rt.title AS movie_title,
    rt.production_year,
    ar.name AS actor_name,
    COALESCE(ar.role_count, 0) AS total_roles,
    cd.company_name,
    cd.company_type,
    CASE
        WHEN rt.title_rank <= 5 THEN 'Top 5 in Year'
        ELSE 'Other Titles'
    END AS title_category
FROM
    RankedTitles rt
LEFT JOIN
    ActorRoleCounts ar ON ar.role_count > 0
LEFT JOIN
    CompanyDetails cd ON cd.company_name IS NOT NULL
WHERE
    rt.production_year >= 2000
    AND (cd.company_type = 'Distributor' OR cd.company_type IS NULL)
GROUP BY
    rt.title,
    rt.production_year,
    ar.name,
    ar.role_count,
    cd.company_name,
    cd.company_type,
    rt.title_rank;
