WITH RankedMovies AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY m.production_year DESC) AS rank
    FROM
        aka_title AS m
    JOIN
        movie_keyword AS mk ON m.id = mk.movie_id
    JOIN
        keyword AS k ON mk.keyword_id = k.id
    WHERE
        m.production_year >= 2000
),
ActorDetails AS (
    SELECT
        a.name AS actor_name,
        c.movie_id,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY c.nr_order) AS role_rank
    FROM
        aka_name AS a
    JOIN
        cast_info AS c ON a.person_id = c.person_id
    WHERE
        c.note IS NOT NULL
),
MovieInfoExtended AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        ad.actor_name,
        COUNT(mi.id) AS info_count
    FROM
        RankedMovies AS rm
    LEFT JOIN
        complete_cast AS cc ON rm.movie_id = cc.movie_id
    LEFT JOIN
        ActorDetails AS ad ON cc.subject_id = ad.movie_id
    LEFT JOIN
        movie_info AS mi ON rm.movie_id = mi.movie_id
    GROUP BY
        rm.movie_id, rm.title, rm.production_year, ad.actor_name
)

SELECT
    mie.movie_id,
    mie.title,
    mie.production_year,
    mie.actor_name,
    mie.info_count,
    CASE
        WHEN mie.production_year < 2010 THEN 'Classic'
        WHEN mie.production_year BETWEEN 2010 AND 2015 THEN 'Modern'
        ELSE 'Recent'
    END AS movie_age_category
FROM
    MovieInfoExtended AS mie
WHERE
    mie.info_count > 0;
