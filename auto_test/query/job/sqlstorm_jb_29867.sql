WITH RankedMovies AS (
    SELECT
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY c.nr_order) AS actor_rank
    FROM
        aka_title t
    JOIN
        cast_info c ON t.id = c.movie_id
    JOIN
        aka_name a ON c.person_id = a.person_id
    WHERE
        t.production_year BETWEEN 2000 AND 2020
),
TitleKeywords AS (
    SELECT
        tm.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
    JOIN
        aka_title tm ON mk.movie_id = tm.id
    GROUP BY
        tm.movie_id
),
MovieInfoExtended AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        ti.info,
        ti.note,
        tk.keywords
    FROM
        aka_title t
    LEFT JOIN
        movie_info ti ON t.id = ti.movie_id
    LEFT JOIN
        TitleKeywords tk ON t.id = tk.movie_id
)
SELECT
    mu.movie_title,
    mu.production_year,
    mu.actor_name,
    mu.actor_rank,
    mi.info,
    mi.keywords
FROM
    RankedMovies mu
LEFT JOIN
    MovieInfoExtended mi ON mu.movie_title = mi.title
WHERE
    mu.actor_rank <= 3;
