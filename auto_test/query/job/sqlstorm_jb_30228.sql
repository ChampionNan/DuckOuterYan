WITH RECURSIVE RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS rank
    FROM 
        aka_title t
)

SELECT 
    p.name AS person_name,
    t.title AS movie_title,
    t.production_year,
    c.role_id,
    COALESCE(k.keyword, 'No Keyword') AS keyword,
    cp.kind AS company_type,
    CASE 
        WHEN mp.note IS NOT NULL THEN 'Notable'
        ELSE 'Regular'
    END AS note_classification
FROM 
    cast_info c
JOIN 
    aka_name p ON c.person_id = p.person_id
JOIN 
    RankedMovies t ON c.movie_id = t.movie_id
LEFT JOIN 
    movie_keyword mk ON t.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_companies mc ON t.movie_id = mc.movie_id
LEFT JOIN 
    company_type cp ON mc.company_type_id = cp.id
LEFT JOIN 
    movie_info mi ON t.movie_id = mi.movie_id 
                   AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'rating')
LEFT JOIN 
    movie_info_idx mp ON t.movie_id = mp.movie_id 
WHERE 
    t.rank <= 10 
    AND t.production_year >= 2000 
    AND p.name IS NOT NULL;
