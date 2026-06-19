WITH RecursiveMovieCTE AS (
    SELECT 
        title.id AS movie_id,
        title.title,
        title.production_year,
        ROW_NUMBER() OVER (PARTITION BY title.production_year ORDER BY title.production_year DESC) AS row_num
    FROM title
    WHERE title.production_year IS NOT NULL
),

CastDetails AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM cast_info ci
    JOIN aka_name ak ON ci.person_id = ak.person_id
    JOIN role_type rt ON ci.role_id = rt.id
),

MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
)

SELECT 
    m.movie_id,
    m.title,
    m.production_year,
    cd.actor_name,
    cd.role_name,
    CASE
        WHEN cd.actor_order = 1 THEN 'Lead'
        WHEN cd.actor_order <= 3 THEN 'Supporting'
        ELSE 'Minor'
    END AS role_category,
    COALESCE(mk.keywords, 'No keywords') AS movie_keywords
FROM RecursiveMovieCTE m
LEFT JOIN CastDetails cd ON m.movie_id = cd.movie_id
LEFT JOIN MovieKeywords mk ON m.movie_id = mk.movie_id
WHERE 
    (m.production_year >= 2000 AND m.production_year < 2023) OR 
    (m.production_year IS NULL);
