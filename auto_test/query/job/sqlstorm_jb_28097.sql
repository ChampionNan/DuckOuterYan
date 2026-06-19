
WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY t.production_year DESC) AS year_rank
    FROM
        aka_title AS t
    JOIN
        movie_keyword AS mk ON t.id = mk.movie_id
    JOIN
        keyword AS k ON mk.keyword_id = k.id
    WHERE
        t.production_year >= 2000
),

DirectorInfo AS (
    SELECT
        c.movie_id,
        a.name AS director_name,
        a.person_id AS director_id
    FROM
        cast_info AS c
    JOIN
        aka_name AS a ON c.person_id = a.person_id
    JOIN
        role_type AS r ON c.role_id = r.id
    WHERE
        r.role = 'Director'
),

MovieDetails AS (
    SELECT
        rm.title,
        rm.production_year,
        di.director_name,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM
        RankedMovies AS rm
    LEFT JOIN
        DirectorInfo AS di ON rm.movie_id = di.movie_id
    LEFT JOIN
        movie_keyword AS mk ON rm.movie_id = mk.movie_id
    LEFT JOIN
        keyword AS k ON mk.keyword_id = k.id
    GROUP BY
        rm.title, rm.production_year, di.director_name
)

SELECT
    md.title,
    md.production_year,
    md.director_name,
    md.keywords
FROM
    MovieDetails AS md
WHERE
    md.director_name IS NOT NULL;
