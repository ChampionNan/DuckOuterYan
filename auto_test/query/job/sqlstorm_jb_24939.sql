
WITH ranked_titles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE
        t.production_year IS NOT NULL
),
actor_movie_info AS (
    SELECT
        ca.movie_id,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ca.movie_id ORDER BY ca.nr_order) AS actor_rank
    FROM
        cast_info ca
    JOIN
        aka_name a ON ca.person_id = a.person_id
),
filtered_movies AS (
    SELECT
        mt.movie_id,
        mt.info_type_id,
        mt.info,
        m.title,
        m.production_year
    FROM
        movie_info mt
    JOIN
        title m ON mt.movie_id = m.id
    WHERE 
        m.production_year >= 2000 
        AND m.production_year <= 2023
        AND mt.info_type_id IN (SELECT id FROM info_type WHERE info LIKE '%award%')
),
keyword_aggregates AS (
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
    r.title AS movie_title,
    r.production_year,
    COALESCE(ka.actor_name, 'Unknown') AS leading_actor,
    kt.keywords,
    COALESCE(ti.info, 'No awards information') AS awards_info,
    CASE 
        WHEN r.title_rank = 1 THEN 'Best Title of the Year'
        WHEN r.title_rank <= 5 THEN 'Top 5 Titles of the Year'
        ELSE 'Others'
    END AS title_category
FROM
    ranked_titles r
LEFT JOIN
    actor_movie_info ka ON r.title_id = ka.movie_id AND ka.actor_rank = 1
LEFT JOIN
    filtered_movies ti ON r.title_id = ti.movie_id
LEFT JOIN
    keyword_aggregates kt ON r.title_id = kt.movie_id
WHERE
    r.title IS NOT NULL
GROUP BY
    r.title_id, r.title, r.production_year, ka.actor_name, kt.keywords, ti.info, r.title_rank;
