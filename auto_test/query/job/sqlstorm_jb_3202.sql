
WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM title t
    WHERE t.production_year IS NOT NULL
),
actor_names AS (
    SELECT
        a.person_id,
        STRING_AGG(DISTINCT a.name, ', ') AS actor_names
    FROM aka_name a
    GROUP BY a.person_id
),
movie_actor_info AS (
    SELECT 
        mc.movie_id AS title_id,
        cn.name AS company_name,
        ca.person_id,
        ra.actor_names,
        COALESCE(mo.note, 'No additional info') AS movie_note
    FROM movie_companies mc
    INNER JOIN company_name cn ON mc.company_id = cn.id
    INNER JOIN complete_cast cc ON mc.movie_id = cc.movie_id
    INNER JOIN cast_info ca ON cc.subject_id = ca.id
    LEFT JOIN movie_info mo ON mc.movie_id = mo.movie_id AND mo.info_type_id = (SELECT id FROM info_type WHERE info = 'Trivia')
    LEFT JOIN actor_names ra ON ca.person_id = ra.person_id
    WHERE ca.role_id = (SELECT id FROM role_type WHERE role = 'Actor')
),
distinct_movies AS (
    SELECT DISTINCT mt.title_id, mt.production_year
    FROM ranked_titles mt
)

SELECT 
    r.title_id,
    r.title,
    r.production_year,
    ma.actor_names,
    ma.company_name,
    ma.movie_note,
    CASE 
        WHEN ma.movie_note IS NULL THEN 'No Note' 
        ELSE ma.movie_note 
    END AS final_note
FROM ranked_titles r
LEFT JOIN movie_actor_info ma ON r.title_id = ma.title_id
WHERE r.rn <= 10;
