
WITH ranked_movies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
extended_cast AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        COALESCE(c.name, 'Unknown Company') AS company_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN 
        movie_companies mc ON ci.movie_id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.imdb_id
    LEFT JOIN 
        role_type r ON ci.role_id = r.id
),
missing_movie_info AS (
    SELECT 
        m.id AS movie_id,
        t.title,
        m.info AS missing_info,
        it.info AS info_type
    FROM 
        movie_info m
    JOIN 
        title t ON m.movie_id = t.id
    LEFT JOIN 
        info_type it ON m.info_type_id = it.id
    WHERE 
        m.info IS NULL
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
    r.movie_id,
    r.title,
    r.production_year,
    ec.actor_name,
    ec.role_name,
    ec.company_name,
    r.year_rank,
    COALESCE(mmi.missing_info, 'No Missing Info') AS missing_movie_info,
    COALESCE(ks.keywords, 'No Keywords') AS keywords,
    CASE 
        WHEN ec.actor_order IS NULL THEN 'Unknown Order'
        ELSE CAST(ec.actor_order AS VARCHAR) || 'th'
    END AS actor_order
FROM 
    ranked_movies r
LEFT JOIN 
    extended_cast ec ON r.movie_id = ec.movie_id
LEFT JOIN 
    missing_movie_info mmi ON r.movie_id = mmi.movie_id
LEFT JOIN 
    keyword_summary ks ON r.movie_id = ks.movie_id
WHERE 
    (r.production_year > 2000 AND r.year_rank <= 5)
    OR (r.production_year < 1950 AND r.year_rank <= 2);
