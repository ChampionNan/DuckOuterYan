WITH movie_details AS (
    SELECT 
        mt.title AS movie_title,
        mt.production_year,
        pc.name AS company_name,
        co.kind AS company_type,
        kw.keyword AS keyword,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM aka_title mt
    JOIN movie_companies mc ON mt.id = mc.movie_id
    JOIN company_name pc ON mc.company_id = pc.id
    JOIN company_type co ON mc.company_type_id = co.id
    JOIN movie_keyword mk ON mt.id = mk.movie_id
    JOIN keyword kw ON mk.keyword_id = kw.id
    LEFT JOIN complete_cast cc ON mt.id = cc.movie_id
    LEFT JOIN cast_info ci ON cc.subject_id = ci.person_id
    WHERE mt.production_year BETWEEN 2000 AND 2023
    GROUP BY mt.title, mt.production_year, pc.name, co.kind, kw.keyword
),
ranked_movies AS (
    SELECT 
        movie_title,
        production_year,
        company_name,
        company_type,
        keyword,
        actor_count,
        RANK() OVER (PARTITION BY production_year ORDER BY actor_count DESC) AS rank
    FROM movie_details
)
SELECT 
    rm.movie_title,
    rm.production_year,
    rm.company_name,
    rm.company_type,
    rm.keyword,
    rm.actor_count,
    rm.rank
FROM ranked_movies rm
WHERE rm.rank <= 5;
