WITH movie_details AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        cc.company_id,
        cc.note AS company_note,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY cc.id) AS company_rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_companies cc ON t.movie_id = cc.movie_id
    WHERE 
        t.production_year >= 2000
),
actor_details AS (
    SELECT 
        c.movie_id,
        ak.person_id,
        ak.name,
        c.nr_order,
        RANK() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    WHERE 
        c.note IS NULL
),
keyword_details AS (
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
    md.title,
    md.production_year,
    ad.name AS actor_name,
    ad.nr_order,
    md.company_note,
    kd.keywords
FROM 
    movie_details md
LEFT JOIN 
    actor_details ad ON md.movie_id = ad.movie_id
LEFT JOIN 
    keyword_details kd ON md.movie_id = kd.movie_id
WHERE 
    md.company_id IS NOT NULL;
