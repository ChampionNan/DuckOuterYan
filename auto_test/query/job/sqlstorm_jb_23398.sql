
WITH RECURSIVE company_movie AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        COALESCE(mi.info, 'No Info') AS movie_info,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY ct.kind) AS rnk
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    LEFT JOIN 
        movie_info mi ON mc.movie_id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Summary')
)

SELECT 
    t.title,
    ak.name AS actor_name,
    CASE 
        WHEN ak.name IS NULL THEN 'Unknown Actor'
        ELSE ak.name
    END AS actor_display_name,
    cm.company_name,
    cm.company_type,
    cm.movie_info,
    CASE 
        WHEN cm.rnk = 1 THEN 'Primary'
        ELSE 'Secondary'
    END AS company_rank
FROM 
    aka_title at
JOIN 
    title t ON at.movie_id = t.id
LEFT JOIN 
    cast_info ci ON t.id = ci.movie_id
LEFT JOIN 
    aka_name ak ON ci.person_id = ak.person_id
LEFT JOIN 
    (SELECT movie_id, COUNT(DISTINCT c.name) AS total_companies
     FROM movie_companies mc
     JOIN company_name c ON mc.company_id = c.id
     GROUP BY mc.movie_id) AS company_counts ON t.id = company_counts.movie_id
LEFT JOIN 
    company_movie cm ON t.id = cm.movie_id
WHERE 
    t.production_year >= 2000 
    AND (t.title ILIKE '%adventure%' OR t.title ILIKE '%fantasy%')
    AND (company_counts.total_companies IS NULL OR company_counts.total_companies > 1)
GROUP BY 
    t.title, ak.name, cm.company_name, cm.company_type, cm.movie_info, cm.rnk;
