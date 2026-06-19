
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS depth,
        CAST(mt.title AS VARCHAR(255)) AS title_path
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL  
    UNION ALL
    SELECT 
        et.id AS movie_id,
        et.title,
        et.production_year,
        mh.depth + 1 AS depth,
        CAST(mh.title_path || ' > ' || et.title AS VARCHAR(255)) AS title_path
    FROM 
        aka_title et
    JOIN 
        movie_hierarchy mh ON et.episode_of_id = mh.movie_id  
),
movie_cast_info AS (
    SELECT 
        c.movie_id,
        p.id AS person_id,
        a.name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        name p ON a.person_id = p.imdb_id
    WHERE 
        p.gender = 'F' OR p.gender = 'M'  
),
keyword_movies AS (
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
joined_data AS (
    SELECT 
        mh.movie_id,
        mh.title_path,
        mh.production_year,
        COALESCE(mc.name, 'Unknown') AS actor_name,
        COALESCE(km.keywords, 'No keywords') AS keywords,
        mh.depth,
        COUNT(mc.person_id) OVER (PARTITION BY mh.movie_id) AS total_cast_members
    FROM 
        movie_hierarchy mh
    LEFT JOIN 
        movie_cast_info mc ON mh.movie_id = mc.movie_id
    LEFT JOIN 
        keyword_movies km ON mh.movie_id = km.movie_id
)
SELECT 
    jd.movie_id,
    jd.title_path,
    jd.production_year,
    jd.actor_name,
    jd.keywords,
    jd.depth,
    jd.total_cast_members,
    
    CASE 
        WHEN jd.depth > 3 THEN 'Deep'
        WHEN jd.depth IS NULL THEN 'Not Applicable'
        ELSE 'Shallow'
    END AS depth_description,
    
    CASE 
        WHEN jd.keywords = 'No keywords' THEN NULL 
        ELSE jd.keywords 
    END AS final_keywords,

    COUNT(*) OVER (PARTITION BY jd.production_year) AS movies_released_same_year
FROM 
    joined_data jd
WHERE 
    jd.production_year IS NOT NULL
GROUP BY 
    jd.movie_id,
    jd.title_path,
    jd.production_year,
    jd.actor_name,
    jd.keywords,
    jd.depth,
    jd.total_cast_members;
