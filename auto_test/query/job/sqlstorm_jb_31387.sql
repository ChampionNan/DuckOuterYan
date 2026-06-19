WITH RECURSIVE MovieCTE AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        COALESCE(substr(m.title, position(' ' in m.title) + 1), 'Unknown') AS secondary_title
    FROM
        aka_title m
    WHERE
        m.production_year >= 2000
    UNION ALL
    SELECT
        m.movie_id,
        m.title,
        m.production_year,
        COALESCE(substr(m.title, position(' ' in m.title) + 1), 'Unknown')
    FROM
        movie_link ml
    JOIN
        aka_title m ON ml.linked_movie_id = m.id
    WHERE
        m.production_year >= 2000 
),
StarringInfo AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS character_role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
),
MovieKeywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
),
FilteredMovies AS (
    SELECT
        m.movie_id,
        m.title,
        m.production_year,
        COALESCE(s.actor_name, 'No Actors') AS primary_actor,
        COALESCE(s.character_role, 'Unknown Role') AS character_role,
        COALESCE(mk.keywords, 'No Keywords') AS keywords
    FROM
        MovieCTE m
    LEFT JOIN
        StarringInfo s ON m.movie_id = s.movie_id AND s.actor_rank = 1
    LEFT JOIN
        MovieKeywords mk ON m.movie_id = mk.movie_id
)
SELECT
    fm.title AS Movie_Title,
    fm.production_year AS Production_Year,
    fm.primary_actor AS Primary_Actor,
    fm.character_role AS Character_Role,
    fm.keywords AS Keywords
FROM
    FilteredMovies fm
WHERE
    NOT EXISTS (
        SELECT 1
        FROM movie_info mi
        WHERE mi.movie_id = fm.movie_id 
        AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Box Office')
    );
