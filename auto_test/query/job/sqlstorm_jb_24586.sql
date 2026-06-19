WITH RankedMovies AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(mk.keyword_id) AS keyword_count
    FROM
        title t
    LEFT JOIN
        movie_keyword mk ON t.id = mk.movie_id
    GROUP BY
        t.id, t.title, t.production_year
),
QualifiedMovies AS (
    SELECT
        rm.title_id,
        rm.title,
        rm.production_year,
        rm.title_rank,
        rm.keyword_count
    FROM
        RankedMovies rm
    WHERE
        rm.keyword_count > 2
        AND rm.title_rank <= 5
),
ActorRoles AS (
    SELECT
        ci.movie_id,
        c.name AS actor_name,
        ct.kind AS role_type,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY c.name) AS role_rank
    FROM
        cast_info ci
    JOIN
        aka_name c ON ci.person_id = c.person_id
    JOIN
        comp_cast_type ct ON ci.person_role_id = ct.id
),
FinalBenchmark AS (
    SELECT
        qm.title,
        qm.production_year,
        ar.actor_name,
        ar.role_type
    FROM
        QualifiedMovies qm
    LEFT JOIN
        ActorRoles ar ON qm.title_id = ar.movie_id
    WHERE
        ar.role_rank IS NULL OR ar.role_rank < 3
)
SELECT
    fb.title,
    fb.production_year,
    COALESCE(fb.actor_name, 'No Actors') AS actor_name,
    COALESCE(fb.role_type, 'No Role Type') AS role_type
FROM
    FinalBenchmark fb
WHERE
    (fb.production_year IS NOT NULL AND fb.production_year >= 2000)
    OR (fb.production_year IS NULL AND fb.title IS NOT NULL);
