WITH RecursiveMovieCasts AS (
    SELECT 
        ca.movie_id,
        ca.person_id,
        coalesce(a.name, c.name) AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ca.movie_id ORDER BY ca.nr_order) AS actor_order,
        COUNT(*) OVER (PARTITION BY ca.movie_id) AS total_cast,
        CASE WHEN ca.note IS NOT NULL THEN 'Notable Role' ELSE 'Standard Role' END AS role_type
    FROM 
        cast_info ca
    LEFT JOIN 
        aka_name a ON a.person_id = ca.person_id
    LEFT JOIN 
        char_name c ON c.imdb_index = a.imdb_index
)
SELECT 
    m.title AS movie_title,
    r.actor_name,
    r.actor_order,
    r.total_cast,
    r.role_type,
    COALESCE(mi.info, 'No additional info') AS movie_info,
    CASE 
        WHEN r.actor_order = 1 THEN 'Lead'
        WHEN r.actor_order <= 3 THEN 'Supporting'
        ELSE 'Minor'
    END AS role_position
FROM 
    RecursiveMovieCasts r
JOIN 
    aka_title m ON m.movie_id = r.movie_id
LEFT JOIN 
    movie_info mi ON mi.movie_id = m.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Synopsis')
WHERE 
    m.production_year = 2021 
    AND r.total_cast > 2 
    AND r.actor_name NOT LIKE '%Unknown%'
    AND mi.info IS NOT NULL;
