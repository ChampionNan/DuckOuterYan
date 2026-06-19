WITH RankedTitles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        rt.role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS role_order
    FROM
        cast_info c
    JOIN
        aka_name a ON a.person_id = c.person_id
    JOIN
        role_type rt ON rt.id = c.role_id
),
MoviesWithNotes AS (
    SELECT
        mt.movie_id,
        STRING_AGG(mn.note, '; ') AS notes
    FROM
        movie_info mn
    JOIN
        aka_title mt ON mt.id = mn.movie_id
    WHERE
        mn.note IS NOT NULL
    GROUP BY
        mt.movie_id
)
SELECT
    rt.title,
    rt.production_year,
    ar.actor_name,
    ar.role,
    mw.notes,
    COUNT(*) OVER (PARTITION BY rt.production_year) AS movies_count,
    COALESCE(mw.notes, 'No notes available') AS note_summary
FROM
    RankedTitles rt
LEFT JOIN
    ActorRoles ar ON rt.title_id = ar.movie_id
LEFT JOIN
    MoviesWithNotes mw ON rt.title_id = mw.movie_id
WHERE
    rt.year_rank <= 10;
