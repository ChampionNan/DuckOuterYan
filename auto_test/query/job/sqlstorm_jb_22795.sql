
WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),

TopMovies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year
    FROM
        RankedMovies rm
    WHERE
        rm.rank <= 10
),

CastDetails AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        ci.nr_order AS role_order,
        COALESCE(role.role, 'Unknown Role') AS role_type
    FROM
        cast_info ci
    JOIN
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN
        role_type role ON ci.role_id = role.id
),

MovieCompanies AS (
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
),

CombinedInfo AS (
    SELECT
        tm.movie_id,
        tm.title,
        tm.production_year,
        cd.actor_name,
        cd.role_order,
        cd.role_type,
        STRING_AGG(DISTINCT mc.company_name, ', ') AS production_companies
    FROM
        TopMovies tm
    LEFT JOIN
        CastDetails cd ON tm.movie_id = cd.movie_id
    LEFT JOIN
        MovieCompanies mc ON tm.movie_id = mc.movie_id
    GROUP BY
        tm.movie_id,
        tm.title,
        tm.production_year,
        cd.actor_name,
        cd.role_order,
        cd.role_type
)

SELECT
    ci.*,
    COALESCE(info.info, 'No Additional Info') AS additional_info,
    CASE 
        WHEN ci.role_order IS NULL THEN 'Role info not available'
        WHEN ci.production_year < 2000 THEN 'Classic Movie'
        ELSE 'Modern Movie'
    END AS movie_category
FROM
    CombinedInfo ci
LEFT JOIN
    movie_info info ON ci.movie_id = info.movie_id AND info.info_type_id = (SELECT id FROM info_type WHERE info = 'Summary')
WHERE
    ci.title ILIKE '%Love%';
