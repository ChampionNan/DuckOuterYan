WITH ranked_movies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS year_rank
    FROM 
        aka_title a
    WHERE 
        a.production_year IS NOT NULL
),
actor_info AS (
    SELECT 
        c.movie_id,
        ak.name AS actor_name,
        ak.surname_pcode,
        c.nr_order,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
),
movie_keywords AS (
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
    rm.title AS movie_title,
    rm.production_year,
    ai.actor_name,
    ai.nr_order,
    COALESCE(mk.keywords, 'No keywords') AS movie_keywords,
    CASE
        WHEN ai.actor_rank = 1 THEN 'Lead Actor'
        WHEN ai.actor_rank <= 3 THEN 'Supporting Actor'
        ELSE 'Minor Role'
    END AS role_description
FROM 
    ranked_movies rm
LEFT JOIN 
    actor_info ai ON rm.movie_id = ai.movie_id
LEFT JOIN 
    movie_keywords mk ON rm.movie_id = mk.movie_id
WHERE 
    rm.year_rank <= 5;
