WITH ranked_titles AS (
    SELECT
        a.id AS title_id,
        a.title,
        a.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS rank
    FROM
        aka_title a
    LEFT JOIN movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
),
filtered_titles AS (
    SELECT
        rt.title_id,
        rt.title,
        rt.production_year,
        rt.keyword
    FROM
        ranked_titles rt
    WHERE
        rt.rank = 1 
),
actor_movie_count AS (
    SELECT
        c.person_id,
        COUNT(DISTINCT c.movie_id) AS movie_count
    FROM
        cast_info c
    GROUP BY
        c.person_id
),
famous_actors AS (
    SELECT
        a.id AS actor_id,
        a.name,
        ac.movie_count
    FROM
        aka_name a
    JOIN actor_movie_count ac ON a.person_id = ac.person_id
    WHERE
        ac.movie_count > 10 
)
SELECT
    f.title,
    f.production_year,
    f.keyword,
    fa.name AS actor_name,
    fa.movie_count
FROM
    filtered_titles f
JOIN
    cast_info c ON f.title_id = c.movie_id
JOIN
    famous_actors fa ON c.person_id = fa.actor_id;
