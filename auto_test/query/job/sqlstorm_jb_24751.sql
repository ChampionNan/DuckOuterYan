
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        it.info AS movie_info,
        ROW_NUMBER() OVER (PARTITION BY mt.id ORDER BY mt.production_year DESC) AS rn,
        mt.production_year
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_info mi ON mt.id = mi.movie_id
    LEFT JOIN 
        info_type it ON mi.info_type_id = it.id
    WHERE 
        mt.production_year IS NOT NULL AND mi.note IS NULL
),
cast_info_with_roles AS (
    SELECT
        ci.movie_id,
        p.name AS person_name,
        ci.note,
        rt.role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_order
    FROM 
        cast_info ci
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
),
keyword_summary AS (
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
    mh.movie_id,
    mh.title,
    mh.movie_info,
    ciwr.person_name,
    ciwr.role,
    ciwr.role_order,
    COALESCE(ks.keywords, 'No Keywords') AS keywords,
    COUNT(*) OVER() AS total_movies,
    CASE 
        WHEN ciwr.role_order = 1 THEN 'Lead Role'
        ELSE 'Supporting Role'
    END AS role_category
FROM 
    movie_hierarchy mh
LEFT JOIN 
    cast_info_with_roles ciwr ON mh.movie_id = ciwr.movie_id
LEFT JOIN 
    keyword_summary ks ON mh.movie_id = ks.movie_id
WHERE 
    mh.rn = 1
AND 
    (mh.title ILIKE '%Action%' OR mh.title ILIKE '%Drama%');
