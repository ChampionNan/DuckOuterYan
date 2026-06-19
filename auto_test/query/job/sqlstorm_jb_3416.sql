
WITH ranked_titles AS (
    SELECT 
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY c.nr_order) AS title_rank,
        t.movie_id
    FROM 
        aka_title t
    JOIN 
        movie_info mi ON t.movie_id = mi.movie_id
    JOIN 
        movie_keyword mk ON t.movie_id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.person_id
    WHERE 
        mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'Box Office')
        AND k.keyword LIKE '%Drama%'
),
company_info AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(DISTINCT cn.name, ', ' ORDER BY cn.name) AS company_names
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        mc.company_type_id IN (SELECT id FROM company_type WHERE kind = 'Production')
    GROUP BY 
        mc.movie_id
)
SELECT 
    rt.title,
    rt.production_year,
    rt.title_rank,
    COALESCE(ci.company_names, 'No Companies') AS companies_involved
FROM 
    ranked_titles rt
LEFT JOIN 
    company_info ci ON rt.movie_id = ci.movie_id
WHERE 
    rt.title_rank = 1;
