WITH RankedTitles AS (
    SELECT
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS title_rank
    FROM
        aka_name a
    JOIN
        cast_info c ON a.person_id = c.person_id
    JOIN
        aka_title t ON c.movie_id = t.movie_id
    WHERE
        t.production_year IS NOT NULL
),
TopActorMovies AS (
    SELECT
        actor_name,
        movie_title,
        production_year
    FROM
        RankedTitles
    WHERE
        title_rank <= 3
),
MovieDetails AS (
    SELECT
        m.title,
        ARRAY_AGG(DISTINCT k.keyword) AS keywords,
        m.production_year,
        c.kind AS company_type
    FROM
        aka_title m
    LEFT JOIN
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN
        movie_companies mc ON m.id = mc.movie_id
    LEFT JOIN
        company_type c ON mc.company_type_id = c.id
    GROUP BY
        m.id, m.title, m.production_year, c.kind
)
SELECT
    tam.actor_name,
    tam.movie_title,
    tam.production_year,
    COALESCE(md.keywords, '{}') AS keywords,
    CASE
        WHEN md.production_year < 2000 THEN 'Classic'
        WHEN md.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS era
FROM
    TopActorMovies tam
LEFT JOIN
    MovieDetails md ON tam.movie_title = md.title
WHERE
    md.company_type IS NULL OR md.company_type != 'Distributor';
