WITH movie_details AS (
    SELECT 
        a.title,
        a.production_year,
        c.name AS company_name,
        k.keyword,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_companies mc ON a.id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id AND c.country_code IS NOT NULL
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON a.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.id
    WHERE 
        a.production_year >= 2000
        AND (k.keyword LIKE '%action%' OR k.keyword LIKE '%drama%')
    GROUP BY 
        a.title, a.production_year, c.name, k.keyword
),
ranked_movies AS (
    SELECT 
        md.*,
        RANK() OVER (PARTITION BY md.production_year ORDER BY md.cast_count DESC) AS rank
    FROM 
        movie_details md
)
SELECT 
    r.title,
    r.production_year,
    r.company_name,
    r.keyword,
    r.cast_count
FROM 
    ranked_movies r
WHERE 
    r.rank <= 5
    AND (r.company_name IS NOT NULL OR r.keyword IS NOT NULL);
