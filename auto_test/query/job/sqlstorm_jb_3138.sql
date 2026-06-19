
WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM title t
    WHERE t.production_year IS NOT NULL
), title_info AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        COALESCE(mi.info, 'No Info') AS additional_info
    FROM ranked_titles rt
    LEFT JOIN movie_info mi ON rt.title_id = mi.movie_id 
    WHERE mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Plot' LIMIT 1)
), cast_details AS (
    SELECT 
        ci.movie_id,
        STRING_AGG(CONCAT(a.name, ' as ', rt.role), ', ') AS cast_list
    FROM cast_info ci
    JOIN aka_name a ON ci.person_id = a.person_id
    JOIN role_type rt ON ci.role_id = rt.id
    GROUP BY ci.movie_id
), full_movie_details AS (
    SELECT 
        ti.title,
        ti.production_year,
        ti.additional_info,
        cd.cast_list,
        ROW_NUMBER() OVER (ORDER BY ti.production_year DESC) AS serial_no
    FROM title_info ti
    LEFT JOIN cast_details cd ON ti.title_id = cd.movie_id
)
SELECT 
    fmd.title,
    fmd.production_year,
    fmd.additional_info,
    COALESCE(fmd.cast_list, 'No Cast Info') AS cast_list,
    fmd.serial_no
FROM full_movie_details fmd
WHERE fmd.production_year >= 2000
AND fmd.cast_list IS NOT NULL;
