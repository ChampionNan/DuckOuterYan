
WITH ranked_movies AS (
    SELECT 
        a.title,
        ak.name AS actor_name,
        ti.info AS additional_info,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY ti.info_type_id) AS rank,
        a.id AS movie_id
    FROM 
        aka_title AS a
    JOIN 
        movie_info AS ti ON a.id = ti.movie_id
    JOIN 
        cast_info AS ci ON a.id = ci.movie_id
    JOIN 
        aka_name AS ak ON ci.person_id = ak.person_id
    WHERE 
        a.production_year >= 2000
        AND ti.info_type_id IN (SELECT id FROM info_type WHERE info LIKE '%rating%')
),
movie_keywords AS (
    SELECT 
        m.id AS movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword AS mk
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    JOIN 
        aka_title AS m ON mk.movie_id = m.id
    GROUP BY 
        m.id
),
companies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies AS mc
    JOIN 
        company_name AS c ON mc.company_id = c.id
    JOIN 
        company_type AS ct ON mc.company_type_id = ct.id
)
SELECT 
    rm.title,
    rm.actor_name,
    rm.additional_info,
    COALESCE(mk.keywords, 'No Keywords') AS keywords,
    c.company_name,
    c.company_type
FROM 
    ranked_movies AS rm
LEFT JOIN 
    movie_keywords AS mk ON rm.movie_id = mk.movie_id
LEFT JOIN 
    companies AS c ON rm.movie_id = c.movie_id
WHERE 
    rm.rank = 1
    AND (c.company_name IS NOT NULL OR c.company_type IS NOT NULL);
