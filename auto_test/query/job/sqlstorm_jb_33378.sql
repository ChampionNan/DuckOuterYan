WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        1 AS depth
    FROM 
        aka_title m
    WHERE 
        m.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
    
    UNION ALL
    
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        mh.depth + 1
    FROM 
        movie_link ml
    JOIN 
        MovieHierarchy mh ON ml.movie_id = mh.movie_id
    JOIN 
        aka_title m ON ml.linked_movie_id = m.id
    WHERE 
        m.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
)

SELECT 
    ak.name AS Actor_Name,
    mt.title AS Movie_Title,
    COALESCE(k.keyword, 'No Keywords') AS Movie_Keyword,
    COUNT(CASE WHEN cc.role_id IS NOT NULL THEN 1 END) OVER (PARTITION BY mt.id) AS Total_Cast,
    CASE 
        WHEN m1.production_year = m2.production_year THEN 'Same Year'
        ELSE 'Different Year'
    END AS Year_Comparison
FROM 
    aka_name ak
JOIN 
    cast_info cc ON ak.person_id = cc.person_id
JOIN 
    aka_title mt ON cc.movie_id = mt.id
LEFT JOIN 
    movie_keyword mk ON mt.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    aka_title m1 ON cc.movie_id = m1.id
LEFT JOIN 
    aka_title m2 ON m1.id IN (SELECT linked_movie_id FROM movie_link WHERE movie_id = m1.id)
WHERE 
    ak.name IS NOT NULL 
    AND mt.production_year IS NOT NULL
    AND (cc.note IS NULL OR cc.note <> 'Cameo')
    AND EXISTS (
        SELECT 1 
        FROM complete_cast cc2 
        WHERE cc2.movie_id = mt.id 
          AND cc2.subject_id = ak.person_id
    );
