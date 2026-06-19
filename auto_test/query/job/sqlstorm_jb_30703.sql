
WITH RECURSIVE actor_hierarchy AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        1 AS level
    FROM 
        aka_name a
    WHERE 
        a.name LIKE 'A%' 

    UNION ALL
    
    SELECT 
        c.person_id AS actor_id,
        ak.name AS actor_name,
        ah.level + 1
    FROM 
        cast_info c
    JOIN 
        actor_hierarchy ah ON c.movie_id IN (
            SELECT 
                m.movie_id 
            FROM 
                movie_companies m
            WHERE 
                m.company_id IN (
                    SELECT 
                        comp.id
                    FROM 
                        company_name comp
                    WHERE 
                        comp.country_code = 'USA'
                )
        )
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    WHERE 
        ah.level < 3 
),
movie_info_extended AS (
    SELECT 
        m.id AS id,
        m.title,
        m.production_year,
        CASE 
            WHEN mi.info IS NULL THEN 'No info available'
            ELSE mi.info
        END AS info_text,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY mi.info_type_id) AS info_rank
    FROM 
        title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
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
    ah.actor_name,
    COALESCE(mie.title, 'No movies') AS movie_title,
    mie.production_year,
    mie.info_text,
    ksw.keywords
FROM 
    actor_hierarchy ah
LEFT JOIN 
    cast_info ci ON ci.person_id = ah.actor_id
LEFT JOIN 
    movie_info_extended mie ON ci.movie_id = mie.id AND mie.info_rank = 1
LEFT JOIN 
    keyword_summary ksw ON ci.movie_id = ksw.movie_id
WHERE 
    ah.level = 1 
    AND (mie.production_year > 2000 OR mie.title LIKE '%Action%');
