WITH RankedMovies AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.title) AS title_rank
    FROM
        aka_title mt
    WHERE
        mt.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT
        ca.movie_id,
        ca.person_id,
        COALESCE(cr.role, 'Unknown') AS role,
        COALESCE(a.name, 'Unnamed Actor') AS actor_name,
        COUNT(ca.person_id) OVER (PARTITION BY ca.movie_id) AS role_count
    FROM
        cast_info ca
    LEFT JOIN role_type cr ON ca.role_id = cr.id
    LEFT JOIN aka_name a ON ca.person_id = a.person_id
),
FilteredMovies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        ar.actor_name,
        ar.role,
        ar.role_count
    FROM
        RankedMovies rm
    LEFT JOIN ActorRoles ar ON rm.movie_id = ar.movie_id
    WHERE
        (ar.role_count > 5 OR ar.role IS NOT NULL)
        AND (rm.production_year BETWEEN 2000 AND 2020)
),
KeywordMovies AS (
    SELECT
        fm.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        FilteredMovies fm
    JOIN movie_keyword mk ON fm.movie_id = mk.movie_id
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY
        fm.movie_id
),
FinalResults AS (
    SELECT
        fm.movie_id,
        fm.title,
        fm.production_year,
        fm.actor_name,
        fm.role,
        km.keywords,
        CASE
            WHEN fm.role IS NULL THEN 'No Role Assigned'
            ELSE fm.role
        END AS adjusted_role
    FROM
        FilteredMovies fm
    LEFT JOIN KeywordMovies km ON fm.movie_id = km.movie_id
)
SELECT
    f.movie_id,
    f.title,
    f.production_year,
    f.actor_name,
    f.adjusted_role,
    COALESCE(f.keywords, 'No Keywords') AS keywords
FROM
    FinalResults f
WHERE
    EXISTS (SELECT 1
            FROM complete_cast cc
            WHERE cc.movie_id = f.movie_id AND cc.subject_id IS NOT NULL);
