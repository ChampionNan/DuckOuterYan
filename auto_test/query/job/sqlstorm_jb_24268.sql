
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        mp.name AS company_name,
        COALESCE(ct.kind, 'Unknown') AS company_type,
        1 AS level
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_companies mc ON mt.id = mc.movie_id
    LEFT JOIN 
        company_name mp ON mc.company_id = mp.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        mt.production_year >= 2000

    UNION ALL

    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        mp.name,
        COALESCE(ct.kind, 'Unknown'),
        mh.level + 1
    FROM 
        movie_hierarchy mh
    JOIN 
        movie_link ml ON mh.movie_id = ml.movie_id
    JOIN 
        aka_title mt ON ml.linked_movie_id = mt.id
    LEFT JOIN 
        movie_companies mc ON mt.id = mc.movie_id
    LEFT JOIN 
        company_name mp ON mc.company_id = mp.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        mh.level < 3 
),
ranked_movies AS (
    SELECT 
        h.movie_id,
        h.title,
        h.production_year,
        h.company_name,
        h.company_type,
        RANK() OVER (PARTITION BY h.production_year ORDER BY h.title) AS title_rank
    FROM 
        movie_hierarchy h
),
keyword_count AS (
    SELECT 
        mt.id AS movie_id,
        COUNT(mk.keyword_id) AS keyword_total
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    GROUP BY 
        mt.id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.company_name,
    rm.company_type,
    COALESCE(kc.keyword_total, 0) AS keyword_count, 
    CASE 
        WHEN COALESCE(kc.keyword_total, 0) > 5 THEN 'High'
        WHEN COALESCE(kc.keyword_total, 0) BETWEEN 2 AND 5 THEN 'Moderate'
        ELSE 'Low'
    END AS keyword_density,
    CONCAT('Movie: ', rm.title, ' (', rm.production_year, '), Produced by: ', rm.company_name) AS movie_detail,
    NULLIF(rm.title_rank, 1) AS rank_adjustment
FROM 
    ranked_movies rm
LEFT JOIN 
    keyword_count kc ON rm.movie_id = kc.movie_id
WHERE 
    rm.title IS NOT NULL 
    AND rm.production_year IS NOT NULL 
    AND (rm.company_name IS NOT NULL OR rm.company_type IS NOT NULL);
