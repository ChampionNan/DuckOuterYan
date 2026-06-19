WITH ranked_titles AS (
    SELECT 
        at.id AS title_id,
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.title) AS title_rank
    FROM 
        aka_title at
    WHERE 
        at.production_year IS NOT NULL
), 
employee_cast AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        COUNT(ci.person_id) AS actor_count
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        ak.name IS NOT NULL
    GROUP BY 
        ci.movie_id, ak.name
), 
company_details AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        cn.name IS NOT NULL
), 
keyword_ranked AS (
    SELECT 
        mk.movie_id,
        k.keyword,
        DENSE_RANK() OVER (ORDER BY k.keyword) AS keyword_rank
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword IS NOT NULL
)

SELECT 
    rt.title AS movie_title,
    rt.production_year AS year,
    ec.actor_name,
    ec.actor_count,
    cd.company_name,
    cd.company_type,
    kr.keyword,
    kr.keyword_rank
FROM 
    ranked_titles rt
LEFT JOIN 
    employee_cast ec ON rt.title_id = ec.movie_id
LEFT JOIN 
    company_details cd ON rt.title_id = cd.movie_id
LEFT JOIN 
    keyword_ranked kr ON rt.title_id = kr.movie_id
WHERE 
    (rt.production_year >= 2000 OR ec.actor_name IS NOT NULL)
    AND (cd.company_type = 'Production' OR cd.company_type IS NULL);
