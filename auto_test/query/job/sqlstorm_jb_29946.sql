WITH ranked_titles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY k.keyword) AS rank
    FROM
        aka_title t
    JOIN
        movie_keyword mk ON t.id = mk.movie_id
    JOIN
        keyword k ON mk.keyword_id = k.id
    WHERE
        t.production_year >= 2000
),
actor_movie_roles AS (
    SELECT
        a.person_id,
        a.name AS actor_name,
        c.movie_id,
        c.nr_order,
        r.role
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
    WHERE
        a.name IS NOT NULL
),
movie_company_details AS (
    SELECT
        m.movie_id,
        m.note AS movie_note,
        co.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies m
    JOIN
        company_name co ON m.company_id = co.id
    JOIN
        company_type ct ON m.company_type_id = ct.id
)
SELECT
    tt.title,
    tt.production_year,
    tt.keyword,
    amr.actor_name,
    amr.nr_order,
    mcd.movie_note,
    mcd.company_name,
    mcd.company_type
FROM
    ranked_titles tt
LEFT JOIN
    actor_movie_roles amr ON tt.title_id = amr.movie_id
LEFT JOIN
    movie_company_details mcd ON tt.title_id = mcd.movie_id
WHERE
    tt.rank = 1;
