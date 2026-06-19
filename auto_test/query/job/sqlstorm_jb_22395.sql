WITH ranked_movies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS year_rank,
        COUNT(*) OVER (PARTITION BY t.production_year) AS year_count
    FROM
        aka_title t
    WHERE
        t.title IS NOT NULL
),

movie_cast AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        CASE
            WHEN c.note IS NULL THEN 'No note provided'
            ELSE c.note
        END AS presentation_note
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
),

company_movie_info AS (
    SELECT
        m.movie_id,
        COALESCE(c.name, 'Unknown Company') AS company_name,
        COALESCE(ct.kind, 'Unknown Type') AS company_type,
        COUNT(*) OVER (PARTITION BY m.movie_id) AS company_count
    FROM
        movie_companies m
    LEFT JOIN
        company_name c ON m.company_id = c.id
    LEFT JOIN
        company_type ct ON m.company_type_id = ct.id
),

keyword_info AS (
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
    rm.movie_id,
    rm.title,
    rm.production_year,
    mc.actor_name,
    mc.role_name,
    cmi.company_name,
    cmi.company_type,
    ki.keywords,
    rm.year_rank,
    rm.year_count,
    CASE
        WHEN mc.actor_name IS NOT NULL THEN 'Has cast'
        ELSE 'No cast information'
    END AS cast_status
FROM
    ranked_movies rm
LEFT JOIN
    movie_cast mc ON rm.movie_id = mc.movie_id
LEFT JOIN
    company_movie_info cmi ON rm.movie_id = cmi.movie_id
LEFT JOIN
    keyword_info ki ON rm.movie_id = ki.movie_id
WHERE
    rm.production_year >= 2000 AND
    (cmi.company_count > 1 OR cmi.company_count IS NULL);
