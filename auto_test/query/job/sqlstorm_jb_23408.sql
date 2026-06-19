WITH RECURSIVE cte_movies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        mt.kind,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        aka_title m
    JOIN 
        kind_type mt ON m.kind_id = mt.id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        m.production_year IS NOT NULL AND
        mt.kind ILIKE '%Drama%'
),
cte_cast AS (
    SELECT 
        c.movie_id,
        p.name AS actor_name,
        ct.kind AS role,
        DENSE_RANK() OVER (PARTITION BY c.movie_id ORDER BY p.name) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name p ON c.person_id = p.person_id
    JOIN 
        comp_cast_type ct ON c.person_role_id = ct.id
    WHERE 
        ct.kind IS NOT NULL
),
ranked_movies AS (
    SELECT 
        cm.movie_id,
        cm.title,
        cm.production_year,
        cm.kind,
        cc.actor_name,
        cc.role,
        cc.actor_rank,
        SUM(1) OVER (PARTITION BY cm.movie_id) AS actor_count
    FROM 
        cte_movies cm
    LEFT JOIN 
        cte_cast cc ON cm.movie_id = cc.movie_id
)

SELECT 
    r.movie_id,
    r.title,
    r.production_year,
    r.kind,
    COALESCE(r.actor_name, 'no actors available') AS actor_name,
    r.role,
    r.actor_rank,
    r.actor_count,
    CASE 
        WHEN r.actor_count > 5 THEN 'High Actor Count' 
        ELSE 'Low Actor Count' 
    END AS actor_count_description
FROM 
    ranked_movies r
WHERE 
    r.production_year >= (SELECT MAX(production_year) FROM aka_title) - 5;
