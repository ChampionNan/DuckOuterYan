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
ActorRoles AS (
    SELECT
        a.name AS actor_name,
        c.movie_id,
        r.role AS role_type,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY c.nr_order) AS role_rank
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
    WHERE
        a.name IS NOT NULL
),
MovieKeywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
)
SELECT
    rm.title,
    rm.production_year,
    ar.actor_name,
    ar.role_type,
    COALESCE(mk.keywords, 'No Keywords') AS keywords
FROM
    RankedMovies rm
LEFT JOIN
    ActorRoles ar ON rm.movie_id = ar.movie_id AND ar.role_rank = 1
LEFT JOIN
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE
    rm.rank <= 5;
