
WITH ranked_movies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS rank
    FROM 
        aka_title a
    JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year >= 2000
),
actor_details AS (
    SELECT 
        c.movie_id,
        p.id AS actor_id,
        CONCAT(p.name, ' (Role: ', r.role, ')') AS actor_detail
    FROM 
        cast_info c
    JOIN 
        aka_name p ON c.person_id = p.person_id
    JOIN 
        role_type r ON c.person_role_id = r.id
),
company_details AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(DISTINCT cn.name, ', ' ORDER BY cn.name) AS company_names
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    GROUP BY 
        mc.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.keyword,
    ad.actor_detail,
    cd.company_names
FROM 
    ranked_movies rm
LEFT JOIN 
    actor_details ad ON rm.movie_id = ad.movie_id
LEFT JOIN 
    company_details cd ON rm.movie_id = cd.movie_id
WHERE 
    rm.rank = 1;
