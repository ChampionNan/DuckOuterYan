WITH ranked_movies AS (
    SELECT 
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC) as year_rank
    FROM aka_title at
    WHERE at.production_year IS NOT NULL
),
actor_info AS (
    SELECT 
        ak.name AS actor_name,
        COUNT(DISTINCT ci.movie_id) AS movie_count
    FROM aka_name ak
    JOIN cast_info ci ON ak.person_id = ci.person_id
    GROUP BY ak.name
),
movie_company_info AS (
    SELECT 
        at.title,
        cn.name AS company_name,
        ct.kind AS company_type,
        COUNT(*) OVER (PARTITION BY at.id) AS num_companies
    FROM aka_title at
    JOIN movie_companies mc ON at.id = mc.movie_id
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    rm.title,
    rm.production_year,
    ai.actor_name,
    ai.movie_count,
    mci.company_name,
    mci.company_type,
    mci.num_companies
FROM ranked_movies rm
LEFT JOIN actor_info ai ON ai.movie_count > 5
LEFT JOIN movie_company_info mci ON rm.title = mci.title
WHERE rm.year_rank <= 3;
