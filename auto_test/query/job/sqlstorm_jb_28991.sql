
WITH ranked_movies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ak.name AS actor_name,
        ak.id AS actor_id,
        ROW_NUMBER() OVER (PARTITION BY mt.id ORDER BY ak.name) AS actor_rank
    FROM 
        aka_title mt
    JOIN 
        cast_info ci ON mt.id = ci.movie_id
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        mt.production_year BETWEEN 2000 AND 2023
),
keyword_aggregated AS (
    SELECT 
        mvk.movie_id,
        STRING_AGG(kw.keyword, ', ') AS all_keywords
    FROM 
        movie_keyword mvk
    JOIN 
        keyword kw ON mvk.keyword_id = kw.id
    GROUP BY 
        mvk.movie_id
),
title_info AS (
    SELECT 
        t.id AS title_id,
        t.title,
        kt.kind AS film_type,
        ti.info AS additional_info
    FROM 
        title t
    LEFT JOIN 
        kind_type kt ON t.kind_id = kt.id
    LEFT JOIN 
        movie_info mi ON t.id = mi.movie_id
    LEFT JOIN 
        info_type ti ON mi.info_type_id = ti.id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.actor_name,
    rm.actor_rank,
    ka.all_keywords,
    ti.film_type,
    ti.additional_info
FROM 
    ranked_movies rm
LEFT JOIN 
    keyword_aggregated ka ON rm.movie_id = ka.movie_id
LEFT JOIN 
    title_info ti ON rm.movie_id = ti.title_id
WHERE 
    rm.actor_rank <= 3;
