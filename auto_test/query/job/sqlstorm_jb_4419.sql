WITH RankedMovies AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.production_year DESC) AS rank
    FROM
        aka_title m
    WHERE
        m.production_year IS NOT NULL
),
ActorCount AS (
    SELECT
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM
        cast_info c
    GROUP BY
        c.movie_id
),
MovieDetails AS (
    SELECT
        m.movie_id,
        m.title,
        m.production_year,
        ac.actor_count,
        COALESCE(mi.info, 'No Info') AS movie_info,
        RANK() OVER (ORDER BY ac.actor_count DESC) AS actor_rank
    FROM
        RankedMovies m
    LEFT JOIN
        ActorCount ac ON m.movie_id = ac.movie_id
    LEFT JOIN
        movie_info mi ON m.movie_id = mi.movie_id
    WHERE
        m.rank <= 10
)
SELECT
    md.title,
    md.production_year,
    md.actor_count,
    md.movie_info,
    CASE
        WHEN md.actor_count IS NULL THEN 'No Actors'
        WHEN md.actor_count > 5 THEN 'Blockbuster'
        ELSE 'Indie'
    END AS classification
FROM
    MovieDetails md
WHERE
    md.actor_rank <= 5;
